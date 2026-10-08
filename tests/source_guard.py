"""Fail a test session whose package source changed while it ran.

Each run pins `behavior.runtime_manifest()` at creation and refuses to continue
after any source change, so an edit during a suite blocks unrelated demo runs.
Results from mixed code versions are not evidence: report the edit, not a flake.
"""

from __future__ import annotations

import pytest

from autoresearch import behavior

_PINNED = pytest.StashKey[dict[str, str]]()
_DRIFT = pytest.StashKey[list[str]]()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[_PINNED] = behavior.runtime_manifest()


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session) -> None:
    pinned = session.config.stash.get(_PINNED, None)
    if pinned is None:
        return
    changed = behavior.drift({"runtime": pinned}, {"runtime": behavior.runtime_manifest()})
    if changed:
        session.config.stash[_DRIFT] = changed
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
