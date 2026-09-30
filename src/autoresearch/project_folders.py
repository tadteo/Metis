"""Host-local folder selection and private, non-overwriting project creation."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any


def browse_folders(path: str = "") -> dict[str, Any]:
    """List directories only; never read files or recurse into project content."""
    folder = Path(path).expanduser().resolve() if path else Path.home().resolve()
    if not folder.is_dir():
        raise ValueError("Choose an existing folder on this host.")
    children = []
    truncated = False
    for index, child in enumerate(folder.iterdir()):
        if index >= 10000:
            truncated = True
            break
        if not child.name.startswith(".") and child.is_dir():
            children.append({"name": child.name, "path": str(child)})
            if len(children) >= 500:
                truncated = True
                break
    return {
        "path": str(folder),
        "parent": str(folder.parent),
        "folders": sorted(children, key=lambda item: item["name"].casefold()),
        "truncated": truncated,
    }


def create_project_folder(root: Path, name: str) -> dict[str, str]:
    """Allocate a fresh empty folder; a project name is never interpreted as a path."""
    parent = root / "projects"
    if parent.is_symlink():
        raise ValueError("The managed project directory must not be a symbolic link.")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "research"
    folder = Path(tempfile.mkdtemp(prefix=f"{slug}-", dir=parent))
    return {"path": str(folder.resolve())}
