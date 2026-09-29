"""Supported runtime primitives preserve the executor's security boundaries."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from autoresearch.runtime_support import ExecutionError, read_text, run_process, write_file


def test_workspace_primitives_reject_symlinks_and_keep_atomic_replacements(tmp_path: Path) -> None:
    outside = tmp_path / "original.txt"
    outside.write_text("retained")
    workspace = tmp_path / "work"
    workspace.mkdir()
    os.link(outside, workspace / "hardlink.txt")
    write_file(workspace, "hardlink.txt", "replacement")
    assert outside.read_text() == "retained"
    assert read_text(workspace, "hardlink.txt", 7) == "replace\n[truncated]"
    assert (workspace / "hardlink.txt").stat().st_mode & 0o777 == 0o600
    (workspace / "symlink.txt").symlink_to(outside)
    with pytest.raises(ExecutionError):
        write_file(workspace, "symlink.txt", "forbidden")
    with pytest.raises(ExecutionError):
        read_text(workspace, "symlink.txt", 100)
    assert outside.read_text() == "retained"


def test_process_control_bounds_both_streams_and_accepts_large_stdin(tmp_path: Path) -> None:
    result = run_process(
        [
            sys.executable,
            "-c",
            "import sys; data = sys.stdin.buffer.read(); "
            "sys.stdout.buffer.write(data); sys.stderr.buffer.write(data); sys.exit(7)",
        ],
        cwd=tmp_path,
        env={"PATH": os.defpath},
        timeout=10,
        limit=4096,
        input_data=b"x" * 131072,
    )
    assert result.stdout == result.stderr == "x" * 4096 + "\n[truncated]"
    assert result.returncode == 7
    assert not result.timed_out
