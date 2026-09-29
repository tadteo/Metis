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
ARCHIVE_NAME = ".autoresearch-reference.zip"
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


def verify_plotting_checkout(plotting: Path) -> None:
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(plotting), "rev-parse", "HEAD"], text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(plotting), "status", "--porcelain", "--untracked-files=no"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PaperOrchestraError("Cannot verify official plotting checkout") from exc
    if revision != PAPERVIZ_REVISION or dirty:
        raise PaperOrchestraError(
            "Plotting source requires a clean checkout of the pinned revision"
        )


def _file_hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise PaperOrchestraError(f"Missing or unsafe plotting asset: {path.name}")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_asset_snapshot(root: Path, files: dict[str, str]) -> None:
    root = root.expanduser().resolve()
    actual = {
        str(path.relative_to(root))
        for folder in (root / "data/PaperBananaBench", root / "style_guides")
        for path in folder.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != set(files):
        raise PaperOrchestraError("Plotting asset file set changed")
    for relative, expected in files.items():
        path = root / relative
        if any((root / parent).is_symlink() for parent in Path(relative).parents):
            raise PaperOrchestraError("Symlink in plotting asset path")
        if _file_hash(path) != expected:
            raise PaperOrchestraError(f"Plotting asset checksum mismatch: {relative}")


def verify_plotting_assets(plotting: Path) -> dict[str, Any]:
    """Derive expected hashes from the checksum-pinned archive, never an install receipt."""
    plotting = plotting.expanduser().resolve()
    verify_plotting_checkout(plotting)
    archive = plotting / ARCHIVE_NAME
    if _file_hash(archive) != DATA_SHA256:
        raise PaperOrchestraError(
            "Official reference dataset checksum mismatch; run paper_orchestra_setup"
        )
    files: dict[str, str] = {}
    with zipfile.ZipFile(archive) as bundle:
        refs = [n for n in bundle.namelist() if n.endswith("diagram/ref.json")]
        if len(refs) != 1:
            raise PaperOrchestraError("Unexpected official reference dataset layout")
        prefix = refs[0][: -len("diagram/ref.json")]
        for entry in bundle.infolist():
            if entry.is_dir() or not entry.filename.startswith(prefix):
                continue
            relative = Path(entry.filename[len(prefix) :])
            if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
                raise PaperOrchestraError("Unsafe reference archive path")
            with bundle.open(entry) as handle:
                hasher = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
                files[str(Path("data/PaperBananaBench") / relative)] = hasher.hexdigest()
    for task in ("diagram", "plot"):
        name = f"data/PaperBananaBench/{task}/ref.json"
        if name not in files:
            raise PaperOrchestraError(f"Official dataset lacks {task} reference examples")
    styles = plotting / "style_guides"
    for path in styles.rglob("*"):
        if path.is_file():
            files[str(path.relative_to(plotting))] = _file_hash(path)
    for task in ("diagram", "plot"):
        if f"style_guides/neurips2025_{task}_style_guide.md" not in files:
            raise PaperOrchestraError(f"Missing official {task} style guide")
    # Untracked files cannot silently supply a supposedly official style guide.
    tracked = set(
        subprocess.check_output(
            ["git", "-C", str(plotting), "ls-files", "style_guides"], text=True
        ).splitlines()
    )
    if {name for name in files if name.startswith("style_guides/")} != tracked:
        raise PaperOrchestraError("Plotting style guides differ from the official tracked files")
    verify_asset_snapshot(plotting, files)
    return {
        "source_revision": PAPERVIZ_REVISION,
        "reference_revision": DATA_REVISION,
        "archive_sha256": DATA_SHA256,
        "files": files,
    }


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
    verify_plotting_checkout(plotting)
    refs = plotting / "data/PaperBananaBench"
    archive = plotting / ARCHIVE_NAME
    if not archive.is_file():
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
            shutil.copyfile(zip_path, archive)
    if not refs.exists():
        with tempfile.TemporaryDirectory(dir=destination) as scratch:
            extracted = Path(scratch) / "extracted"
            extract_reference_archive(archive, extracted)
            candidates = list(extracted.rglob("diagram/ref.json"))
            if len(candidates) != 1:
                raise PaperOrchestraError("Unexpected official reference dataset layout")
            source = candidates[0].parent.parent
            if not (source / "plot/ref.json").is_file():
                raise PaperOrchestraError("Official dataset lacks plotting reference examples")
            refs.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(refs))
    provenance = verify_plotting_assets(plotting)
    return {
        "plotting_provenance": provenance,
        "checkout_dir": str(writer),
        "paperbanana_dir": str(plotting),
        "writer_revision": UPSTREAM_REVISION,
        "plotting_revision": PAPERVIZ_REVISION,
        "reference_revision": DATA_REVISION,
        "reference_sha256": DATA_SHA256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = provision(args.destination)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
