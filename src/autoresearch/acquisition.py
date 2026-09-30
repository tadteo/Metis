"""Bounded, credential-free resource acquisition for the existing coding tool loop."""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from .runtime_support import ExecutionError, relative_parts
from .source_policy import source_is_excluded

if TYPE_CHECKING:
    from .coding import CodingAction, CodingSession


def acquire(session: CodingSession, action: CodingAction) -> dict[str, Any]:
    try:
        return _acquire(session, action)
    except (httpx.HTTPError, zipfile.BadZipFile) as exc:
        raise ExecutionError(f"Resource acquisition failed: {type(exc).__name__}") from exc


def _acquire(session: CodingSession, action: CodingAction) -> dict[str, Any]:
    """Repository archives must identify an immutable commit; data retains byte identity."""
    parts = urlsplit(action.url)
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in {None, 443}
        or parts.hostname not in session.config.execution.resource_hosts
    ):
        raise ExecutionError("Resource host is not permitted by the run's acquisition policy")
    session.ensure_editable(action.path)
    if action.archive:
        if not re.fullmatch(r"[a-f0-9]{40}", action.revision) or action.revision not in parts.path:
            raise ExecutionError(
                "Repository acquisition requires a URL pinned to its 40-character commit"
            )
    elif action.revision:
        raise ExecutionError("Revision is only valid for repository archives")
    if action.sha256 and not re.fullmatch(r"[a-f0-9]{64}", action.sha256):
        raise ExecutionError("Expected SHA-256 must be 64 hexadecimal characters")
    resources = session.store.run_dir(session.state.id) / "resources"
    resources.mkdir(mode=0o700, exist_ok=True)
    intent = hashlib.sha256(action.model_dump_json().encode()).hexdigest()
    receipt_path = resources / f"{intent}.json"
    import json

    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
    else:
        temporary = resources / f"{intent}.partial"
        digest = hashlib.sha256()
        count = 0
        with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", action.url) as response, temporary.open("wb") as stream:
                response.raise_for_status()
                for block in response.iter_bytes(1024 * 1024):
                    count += len(block)
                    if count > session.config.execution.max_resource_bytes:
                        raise ExecutionError("Resource exceeds the configured acquisition limit")
                    digest.update(block)
                    stream.write(block)
        actual = digest.hexdigest()
        if action.sha256 and action.sha256 != actual:
            raise ExecutionError("Acquired resource does not match its expected SHA-256")
        target = resources / actual
        os.replace(temporary, target)
        target.chmod(0o600)
        receipt = {
            "url": action.url,
            "sha256": actual,
            "bytes": count,
            "revision": action.revision,
            "supplied_sha256": bool(action.sha256),
            "blob": str(target.relative_to(session.store.run_dir(session.state.id))),
        }
        receipt_path.write_text(json.dumps(receipt))
        receipt_path.chmod(0o600)
    blob = session.store.run_dir(session.state.id) / receipt["blob"]
    entries = []
    if action.archive:
        with zipfile.ZipFile(blob) as archive:
            members = archive.infolist()
            if (
                len(members) > 20000
                or sum(item.file_size for item in members)
                > session.config.execution.max_resource_bytes
            ):
                raise ExecutionError("Repository archive exceeds extraction limits")
            for member in members:
                if member.is_dir():
                    continue
                if (member.external_attr >> 16) & 0o170000 not in {0, 0o100000}:
                    raise ExecutionError("Repository archive contains links or special files")
                relative_parts(member.filename)
                # Public archive providers add one repository-root directory.
                suffix = member.filename.split("/", 1)[-1]
                if source_is_excluded(Path(suffix)):
                    continue
                destination = f"{action.path}/{suffix}"
                session.ensure_editable(destination)
                content = archive.read(member)
                actual = hashlib.sha256(content).hexdigest()
                saved = resources / actual
                if not saved.exists():
                    saved.write_bytes(content)
                    saved.chmod(0o600)
                entries.append(
                    {
                        "path": destination,
                        "blob": str(saved.relative_to(session.store.run_dir(session.state.id))),
                        "sha256": actual,
                    }
                )
    else:
        entries = [{"path": action.path, "blob": receipt["blob"], "sha256": receipt["sha256"]}]
    from .runtime_support import file_identity

    for entry in entries:
        target = session.root / entry["path"]
        if (
            target.exists()
            and file_identity(session.root, entry["path"])["sha256"] != entry["sha256"]
        ):
            raise ExecutionError("Acquisition will not overwrite conflicting source")
    import shutil

    from .runtime_support import parent_descriptor

    session.record.setdefault("resources", [])
    for entry in entries:
        if entry not in session.record["resources"]:
            session.record["resources"].append(entry)
    session.save()
    for entry in entries:
        if (session.root / entry["path"]).exists():
            continue
        with parent_descriptor(session.root, entry["path"], create=True) as (parent, name):
            temporary_name = ".autoresearch-acquire-" + entry["sha256"]
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            with (
                os.fdopen(descriptor, "wb") as output,
                (session.store.run_dir(session.state.id) / entry["blob"]).open("rb") as source,
            ):
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, name, src_dir_fd=parent, dst_dir_fd=parent)
    return {"receipt": receipt, "materialized": entries}


def materialize(store_root: Path, destination: Path, entries: list[dict[str, str]]) -> None:
    """Apply only run-owned, content-addressed resources exported by the coding harness."""
    import shutil

    from .runtime_support import file_identity, parent_descriptor

    for entry in entries:
        relative_parts(entry["path"])
        if entry["blob"] != f"resources/{entry['sha256']}" or not re.fullmatch(
            r"[a-f0-9]{64}", entry["sha256"]
        ):
            raise ExecutionError("Invalid run-owned resource identity")
        if (destination / entry["path"]).exists():
            if file_identity(destination, entry["path"])["sha256"] == entry["sha256"]:
                continue
            raise ExecutionError("Resource export conflicts with existing source")
        blob = store_root / entry["blob"]
        with blob.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != entry["sha256"]:
                raise ExecutionError("Acquired resource changed")
            source.seek(0)
            with parent_descriptor(destination, entry["path"], create=True) as (parent, name):
                descriptor = os.open(
                    name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
                )
                with os.fdopen(descriptor, "wb") as output:
                    shutil.copyfileobj(source, output)
