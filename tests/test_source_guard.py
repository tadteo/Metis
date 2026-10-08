"""The session guard turns a source edit during a suite into an explicit failure."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).parent


def run_session(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "test_inner.py").write_text(body)
    path = os.pathsep.join([str(TESTS), os.environ.get("PYTHONPATH", "")])
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "source_guard", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": path},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_source_edit_during_session_fails_and_names_the_file(tmp_path: Path) -> None:
    # Simulates an editor writing into the package between session start and finish.
    done = run_session(
        tmp_path,
        "from autoresearch import behavior\n\n"
        "def test_edit():\n"
        "    current = behavior.runtime_manifest()\n"
        "    behavior.runtime_manifest = lambda: {**current, 'edited_mid_session.py': '0' * 64}\n",
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "1 passed" in done.stdout
    assert "package source changed during this test session" in done.stdout
    assert "runtime file added: edited_mid_session.py" in done.stdout


def test_unchanged_source_keeps_session_status(tmp_path: Path) -> None:
    done = run_session(tmp_path, "def test_nothing():\n    pass\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "package source changed" not in done.stdout
