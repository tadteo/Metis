"""Fail a test session whose package source changed while it ran.

Each run pins `behavior.runtime_manifest()` at creation and refuses to continue
after any source change, so an edit during a suite blocks unrelated demo runs.
Results from mixed code versions are not evidence: report the edit, not a flake.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from autoresearch import behavior

_PINNED = pytest.StashKey[dict[str, str]]()
_DRIFT = pytest.StashKey[list[str]]()


def package_manifest() -> dict[str, str]:
    """The pinned runtime plus every other package file, including the default specs."""
    root = Path(behavior.__file__).parent
    files = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    return {**files, **behavior.runtime_manifest()}


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[_PINNED] = package_manifest()


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session) -> None:
    pinned = session.config.stash.get(_PINNED, None)
    if pinned is None:
        return
    changed = behavior.drift({"runtime": pinned}, {"runtime": package_manifest()})
    if changed:
        session.config.stash[_DRIFT] = changed
        # Keep a more specific status (interrupt, internal or usage error).
        if session.exitstatus in {pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED}:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    changed = config.stash.get(_DRIFT, None)
    if not changed:
        return
    terminalreporter.write_sep("!", "package source changed during this test session", red=True)
    terminalreporter.write_line(
        "Runs pin their source, so edits block them mid-run and results mix code versions."
    )
    terminalreporter.write_line("Rerun on an unchanged checkout. Changed:")
    for item in changed:
        terminalreporter.write_line(f"  {item}")
