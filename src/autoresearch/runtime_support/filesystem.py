"""Race-resistant private workspace access without symlink traversal.

The reserved `.autoresearch-` prefix belongs to runtime control files. Model tools
must use the default `internal=False`; only trusted runtime callers may opt in.
"""

from __future__ import annotations

import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import ExecutionError

_PREFIX = ".autoresearch-"


def relative_parts(relative: str, *, internal: bool = False) -> list[str]:
    pieces = relative.split("/")
    if (
        not relative
        or "\\" in relative
        or "\x00" in relative
        or any(piece in {"", ".", ".."} for piece in pieces)
        or any(":" in piece for piece in pieces)
        or any(piece == ".git" for piece in pieces)
        or (not internal and any(piece.startswith(_PREFIX) for piece in pieces))
    ):
        raise ExecutionError("File paths must be relative, contained workspace paths")
    return pieces


@contextmanager
def parent_descriptor(
    root: Path, relative: str, *, create: bool = False, internal: bool = False
) -> Iterator[tuple[int, str]]:
    """Walk directory descriptors without following symlinks, including races."""
    pieces = relative_parts(relative, internal=internal)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for piece in pieces[:-1]:
            if create:
                try:
                    os.mkdir(piece, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(
                piece, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor, pieces[-1]
    except OSError:
        raise ExecutionError(
            "Workspace path is missing, inaccessible, or contains a symlink"
        ) from None
    finally:
        os.close(descriptor)


def write_file(root: Path, relative: str, value: str | bytes, *, internal: bool = False) -> None:
    with parent_descriptor(root, relative, create=True, internal=internal) as (descriptor, name):
        # Replacing a directory entry avoids changing any other hardlink to an
        # existing file. Both symlinks and special files are rejected first.
        try:
            mode = os.stat(name, dir_fd=descriptor, follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode):
                raise ExecutionError("Experiment files must be regular files")
        except FileNotFoundError:
            pass
        temporary = f"{_PREFIX}write-{uuid.uuid4().hex}"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(value.encode("utf-8") if isinstance(value, str) else value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
        finally:
            try:
                os.unlink(temporary, dir_fd=descriptor)
            except FileNotFoundError:
                pass


def read_text(root: Path, relative: str, limit: int, *, internal: bool = False) -> str:
    with parent_descriptor(root, relative, internal=internal) as (descriptor, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ExecutionError("Experiment files must be regular files")
            data = handle.read(limit + 1)
    if len(data) > limit:
        return data[:limit].decode("utf-8", errors="replace") + "\n[truncated]"
    return data.decode("utf-8", errors="replace")


def file_identity(root: Path, relative: str) -> dict[str, str | int]:
    """Hash exact bytes, including binary/large resources, without following links."""
    import hashlib

    with parent_descriptor(root, relative) as (descriptor, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ExecutionError("Artifact identity requires a regular file")
            size = 0
            digest = hashlib.sha256()
            while block := handle.read(1024 * 1024):
                digest.update(block)
                size += len(block)
    return {"sha256": digest.hexdigest(), "bytes": size}


def copy_file(source_root: Path, relative: str, destination_root: Path) -> None:
    """Stream a regular artifact into a new destination without loading data into memory."""
    import shutil

    with parent_descriptor(source_root, relative) as (source_fd, source_name):
        descriptor = os.open(
            source_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_fd
        )
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ExecutionError("Artifact copy requires a regular file")
            with parent_descriptor(destination_root, relative, create=True) as (
                target_fd,
                target_name,
            ):
                fd = os.open(
                    target_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=target_fd,
                )
                with os.fdopen(fd, "wb") as target:
                    shutil.copyfileobj(source, target)
