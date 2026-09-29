"""Fail-closed migration checks for independently checkpointed legacy work.

Call under the run's existing lease. No process is killed, job resubmitted,
reservation settled, or historical attempt deleted by this inspection.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Protocol

from .contracts import AgentOutput, RunState
from .runtime_support import parent_descriptor


class LegacyStore(Protocol):
    """Public Store operations needed to inspect migration readiness."""

    def get_run(self, run_id: str) -> RunState: ...
    def run_dir(self, run_id: str) -> Path: ...
    def outstanding_calls(self, run_id: str) -> list[dict[str, Any]]: ...


def _unresolved(label: str) -> ValueError:
    return ValueError(
        f"reconcile legacy {label} with the original installation before adopting current behavior; "
        "all checkpoints and failed attempts have been preserved"
    )


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate checkpoint field")
        result[name] = value
    return result


def _record(root: Path, path: Path, label: str) -> dict[str, Any]:
    """Read a bounded journal through verified directory descriptors, including parent races."""
    descriptor = None
    try:
        with parent_descriptor(root, path.relative_to(root).as_posix()) as (parent, name):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("checkpoint must be a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            content = stream.read(64_000_001)
        if len(content) > 64_000_000:
            raise ValueError("checkpoint exceeds the inspection limit")
        value = json.loads(content, object_pairs_hook=_object)
        if not isinstance(value, dict):
            raise ValueError("checkpoint must be an object")
        return value
    except (OSError, ValueError, UnicodeError):
        raise _unresolved(label + " journal (missing, invalid, or unsafe)") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _sessions(root: Path, family: str) -> list[Path]:
    folder = root / family
    try:
        mode = folder.lstat().st_mode
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(mode):
        raise _unresolved(family + " journal directory (unsafe)")
    sessions = sorted(folder.iterdir())
    for session in sessions:
        if not stat.S_ISDIR(session.lstat().st_mode):
            raise _unresolved(family + " session directory (unsafe)")
    return sessions


def _finished_output(record: dict[str, Any], key: str, label: str) -> None:
    if record.get("schema_version") != 1 or not record.get(key):
        raise _unresolved(label + " session")
    try:
        AgentOutput.model_validate(record[key])
    except ValueError:
        raise _unresolved(label + " completion record (invalid)") from None


def assert_no_pending_work(store: LegacyStore, run_id: str) -> None:
    """Reject legacy adoption until top-level, specialist and billing work is reconciled.

    A dead local PID, a failure marker or a zero-dollar reservation does not prove
    that remote execution has stopped or its charge is known. Incomplete historical
    sessions remain unresolved until reconciled under their original implementation.
    """
    state = store.get_run(run_id)
    if state.pending_experiment or state.active_output or state.batch_results:
        raise _unresolved("experiment checkpoint")
    if store.outstanding_calls(run_id):
        raise _unresolved("model-call reservations")
    root = store.run_dir(run_id)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise _unresolved("run directory (unsafe)")
    for session in _sessions(root, "coding"):
        record = _record(root, session / "checkpoint.json", "coding")
        _finished_output(record, "completed", "coding")
        pending = record.get("pending")
        # A normal finish checkpoint retains its final finish proposal. An old
        # in-flight command receipt must still be reconciled even beside a result.
        if pending is not None:
            if not isinstance(pending, dict) or pending.get("started") or pending.get("job_id"):
                raise _unresolved("coding command")
            output = pending.get("output", {})
            plans = output.get("plans", []) if isinstance(output, dict) else []
            if (
                not isinstance(plans, list)
                or len(plans) != 1
                or not isinstance(plans[0], dict)
                or plans[0].get("tool") != "finish"
            ):
                raise _unresolved("coding action")
    for session in _sessions(root, "inspection"):
        record = _record(root, session / "checkpoint.json", "inspection")
        _finished_output(record, "output", "inspection")
    for session in _sessions(root, "paper_orchestra"):
        completed = _record(root, session / "completed.json", "writer completion")
        if completed.get("schema_version") != 1 or not all(
            isinstance(completed.get(key), str) and re.fullmatch(r"[a-f0-9]{64}", completed[key])
            for key in ("pdf_sha256", "source_sha256")
        ):
            raise _unresolved("writer completion")
        accounting = _record(root, session / "accounting.json", "writer accounting")
        if accounting.get("schema_version") == 1:
            attempts = accounting.get("attempts")
            if (
                not isinstance(attempts, list)
                or not attempts
                or any(
                    not isinstance(attempt, dict) or attempt.get("settled") is not True
                    for attempt in attempts
                )
            ):
                raise _unresolved("writer accounting")
        elif "schema_version" in accounting or accounting.get("status") != "settled":
            raise _unresolved("writer accounting")
