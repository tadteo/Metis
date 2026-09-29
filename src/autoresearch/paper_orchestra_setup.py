"""Provision pinned official writer/plotting sources and reference data, without credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import httpx

from .paper_orchestra import UPSTREAM_REVISION, UPSTREAM_URL, PaperOrchestraError, verify_checkout

PAPERVIZ_URL = "https://github.com/google-research/papervizagent.git"
PAPERVIZ_REVISION = "e088a8fff74cc363b6897c0843631fff76484908"
DATA_REVISION = "a876264bcd1e826a0320f805f8fb1cd705cf510f"
DATA_SHA256 = "a980d23954c0cb47017cdaa8a9029dbea3598791fd269a457482033821927e37"
DATA_URL = f"https://huggingface.co/datasets/dwzhu/PaperBananaBench/resolve/{DATA_REVISION}/PaperBananaBench.zip"


def extract_reference_archive(archive: Path, destination: Path) -> None:
    """Extract only validated relative regular files; never symlinks or zip traversal."""
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            relative = Path(entry.filename)
            if relative.is_absolute() or ".." in relative.parts or "\\" in entry.filename:
                raise PaperOrchestraError("Unsafe path in official reference archive")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise PaperOrchestraError("Symlink in official reference archive")
            if entry.file_size > 100_000_000:
                raise PaperOrchestraError("Oversize reference file")
        if sum(e.file_size for e in bundle.infolist()) > 2_000_000_000:
            raise PaperOrchestraError("Reference archive exceeds extraction budget")
        for entry in bundle.infolist():
            target = destination / entry.filename
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, target.open("xb") as out:
                    shutil.copyfileobj(source, out)


def provision(destination: Path) -> dict[str, Any]:
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    writer = destination / "paper-orchestra"
    if not writer.exists():
        subprocess.run(["git", "clone", UPSTREAM_URL, str(writer)], check=True)
        subprocess.run(
            ["git", "-C", str(writer), "checkout", "--detach", UPSTREAM_REVISION], check=True
        )
    verify_checkout(writer)
    plotting = destination / "PaperBanana"
    if not plotting.exists():
        subprocess.run(["git", "clone", PAPERVIZ_URL, str(plotting)], check=True)
        subprocess.run(
            ["git", "-C", str(plotting), "checkout", "--detach", PAPERVIZ_REVISION], check=True
        )
    revision = subprocess.check_output(
        ["git", "-C", str(plotting), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != PAPERVIZ_REVISION:
        raise PaperOrchestraError("Plotting source is not the pinned official revision")
    refs = plotting / "data/PaperBananaBench"
    manifest_path = plotting / "reference-provenance.json"
    if refs.exists() and not manifest_path.exists():
        raise PaperOrchestraError(
            "Existing reference directory has no verified provenance; provision into a fresh destination"
        )
    if not refs.exists():
        with tempfile.TemporaryDirectory(dir=destination) as scratch:
            zip_path = Path(scratch) / "references.zip"
            hasher = hashlib.sha256()
            with httpx.Client(trust_env=False, timeout=120, follow_redirects=True) as client:
                with client.stream("GET", DATA_URL) as response, zip_path.open("wb") as handle:
                    response.raise_for_status()
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > 300_000_000:
                            raise PaperOrchestraError(
                                "Reference download exceeds pinned size budget"
                            )
                        hasher.update(chunk)
                        handle.write(chunk)
            if hasher.hexdigest() != DATA_SHA256:
                raise PaperOrchestraError("Official reference dataset checksum mismatch")
            extracted = Path(scratch) / "extracted"
            extract_reference_archive(zip_path, extracted)
            candidates = list(extracted.rglob("diagram/ref.json"))
            if len(candidates) != 1:
                raise PaperOrchestraError("Unexpected official reference dataset layout")
            source = candidates[0].parent.parent
            if not (source / "plot/ref.json").is_file():
                raise PaperOrchestraError("Official dataset lacks plotting reference examples")
            refs.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(refs))
        manifest = {
            "dataset_revision": DATA_REVISION,
            "archive_sha256": DATA_SHA256,
            "files": {
                str(path.relative_to(refs)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in refs.rglob("*")
                if path.is_file()
            },
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    verify_plotting_materials(plotting)
    return {
        "checkout_dir": str(writer),
        "paperbanana_dir": str(plotting),
        "writer_revision": UPSTREAM_REVISION,
        "plotting_revision": PAPERVIZ_REVISION,
        "reference_revision": DATA_REVISION,
        "reference_sha256": DATA_SHA256,
    }


def verify_plotting_materials(root: Path) -> None:
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != PAPERVIZ_REVISION:
        raise PaperOrchestraError("Plotting style source revision is not pinned")
    subprocess.run(
        ["git", "-C", str(root), "diff", "--exit-code", "HEAD", "--", "style_guides"],
        check=True,
        capture_output=True,
    )
    manifest_path = root / "reference-provenance.json"
    if not manifest_path.is_file():
        raise PaperOrchestraError(
            "Run paper_orchestra_setup to verify plotting reference provenance"
        )
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("archive_sha256") != DATA_SHA256
        or manifest.get("dataset_revision") != DATA_REVISION
    ):
        raise PaperOrchestraError("Plotting reference archive revision/checksum mismatch")
    refs = root / "data/PaperBananaBench"
    for relative, expected in manifest["files"].items():
        path = refs / relative
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(refs.resolve())
            or not path.is_file()
        ):
            raise PaperOrchestraError("Invalid plotting reference file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise PaperOrchestraError("Plotting reference file checksum mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = provision(args.destination)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
