"""Independent regressions from the managed-SSH review; no remote host is contacted."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from autoresearch.remote import RemoteError, RemoteManager, RemoteProfile
from autoresearch.ssh_auth import AuthenticationSession


def wait_until(predicate: Callable[[], bool], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("Synthetic process did not reach the expected state")


def test_shutdown_cannot_miss_a_child_between_admission_and_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = RemoteManager(tmp_path)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    popen = subprocess.Popen
    failures: list[BaseException] = []

    def delayed_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        entered.set()
        assert release.wait(5)
        return popen(*args, **kwargs)

    def operation() -> None:
        try:
            manager._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=30)
        except RemoteError:
            pass  # Rejection during shutdown is also a valid outcome.
        except BaseException as error:
            failures.append(error)

    def close() -> None:
        try:
            manager.close()
        except BaseException as error:
            failures.append(error)
        finally:
            closed.set()

    monkeypatch.setattr("autoresearch.remote.subprocess.Popen", delayed_popen)
    worker = threading.Thread(target=operation)
    closer = threading.Thread(target=close)
    worker.start()
    escaped = False
    try:
        assert entered.wait(2)
        closer.start()
        # Old behavior returns here before the blocked child is registered. Correct
        # admission holds shutdown until the new child can enter the cleanup set.
        closed.wait(0.2)
        release.set()
        assert closed.wait(5)
        worker.join(timeout=2)
        escaped = worker.is_alive() or any(p.poll() is None for p in manager._children)
    finally:
        release.set()
        for process in list(manager._children):
            manager._terminate(process)
        worker.join(timeout=5)
        if closer.ident is not None:
            closer.join(timeout=5)
        manager.close()
    assert not failures
    assert not escaped, "Shutdown returned while a newly admitted SSH child was still running"


def test_successful_authentication_discards_delayed_terminal_echo(tmp_path: Path) -> None:
    ready, emit, emitted = (tmp_path / name for name in ["ready", "emit", "emitted"])
    program = (
        "import sys,time\nfrom pathlib import Path\n"
        "print('Password:',flush=True)\nanswer=input()\n"
        "ready,emit,emitted=map(Path,sys.argv[1:])\nready.touch()\n"
        "while not emit.exists(): time.sleep(.01)\n"
        "print('Delayed echo: '+answer,flush=True)\nemitted.touch()\ntime.sleep(30)\n"
    )
    session = AuthenticationSession(
        [sys.executable, "-c", program, str(ready), str(emit), str(emitted)], ready.exists
    )
    try:
        wait_until(lambda: "Password:" in session.result()["output"])
        session.answer("synthetic-private-response")
        wait_until(lambda: session.result()["status"] == "authenticated")
        emit.touch()
        wait_until(emitted.exists)
        # Allow the watcher to consume a chunk emitted strictly after authentication.
        time.sleep(0.3)
        assert "synthetic-private-response" not in json.dumps(session.result())
        assert "synthetic-private-response" not in session._output
        assert session._process is not None and session._process.poll() is None
    finally:
        session.close()


@pytest.mark.parametrize("outcome", ["failed", "expired"])
def test_terminal_authentication_forgets_responses_and_closes_pty(
    tmp_path: Path, outcome: str
) -> None:
    end = "raise SystemExit(255)" if outcome == "failed" else "time.sleep(30)"
    program = (
        "import time\nprint('Password:',flush=True)\nanswer=input()\n"
        "print('Echo:'+answer,flush=True)\n" + end
    )
    session = AuthenticationSession([sys.executable, "-c", program], lambda: False, timeout=2.0)
    try:
        wait_until(lambda: "Password:" in session.result()["output"])
        session.answer("synthetic-rejected-response")
        wait_until(lambda: session.result()["status"] == outcome and session._fd is None)
        assert session._answers == []
        assert "synthetic-rejected-response" not in session._output
        assert session._process is not None and session._process.poll() is not None
    finally:
        session.close()


def test_failed_authentication_reaps_proxy_child_after_parent_exit(tmp_path: Path) -> None:
    child_file = tmp_path / "child.pid"
    program = (
        "import os,signal,sys,time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGHUP,signal.SIG_IGN)\np=Path(sys.argv[1])\n"
        "if os.fork()==0:\n p.write_text(str(os.getpid()))\n time.sleep(30)\n os._exit(0)\n"
        "while not p.exists(): time.sleep(.01)\nraise SystemExit(255)\n"
    )
    session = AuthenticationSession([sys.executable, "-c", program, str(child_file)], lambda: False)
    child_pid: int | None = None

    def child_stopped() -> bool:
        result = subprocess.run(
            ["ps", "-p", str(child_pid), "-o", "stat="], capture_output=True, text=True, timeout=2
        )
        state = result.stdout.strip()
        return not state or state.startswith("Z")

    try:
        wait_until(child_file.exists)
        child_pid = int(child_file.read_text())
        wait_until(lambda: session.result()["status"] == "failed" and session._fd is None)
        wait_until(child_stopped)
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        session.close()


def test_host_key_approval_is_explicit_and_reconnect_remains_noninteractive(tmp_path: Path) -> None:
    manager = RemoteManager(tmp_path)
    profile = RemoteProfile(name="fixture", host="user@cluster.example")
    try:
        interactive = manager._base(profile, batch=False)
        background = manager._base(profile, batch=True)
        assert "StrictHostKeyChecking=ask" in interactive
        assert "BatchMode=no" in interactive
        assert "StrictHostKeyChecking=yes" in background
        assert "BatchMode=yes" in background
        assert "ForwardAgent=no" in interactive and "ForwardAgent=no" in background
    finally:
        manager.close()


def test_repeated_authentication_cleanup_does_not_signal_a_reusable_process_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AuthenticationSession(
        [sys.executable, "-c", "import time; print('Waiting',flush=True); time.sleep(30)"],
        lambda: False,
    )
    signaled: list[int] = []
    killpg = os.killpg

    def record(group: int, value: int) -> None:
        signaled.append(group)
        killpg(group, value)

    try:
        wait_until(lambda: "Waiting" in session.result()["output"])
        monkeypatch.setattr("autoresearch.ssh_auth.os.killpg", record)
        session.close()
        original = list(signaled)
        session.close()
        assert original
        assert signaled == original, (
            "A disposed process group ID can later belong to another process"
        )
    finally:
        session.close()


def test_failed_termination_is_reported_without_retaining_authentication_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AuthenticationSession(
        [
            sys.executable,
            "-c",
            "import signal,time; signal.signal(signal.SIGHUP,signal.SIG_IGN); print('Password:',flush=True); time.sleep(30)",
        ],
        lambda: False,
    )

    def denied() -> None:
        raise PermissionError("Synthetic signal denial")

    try:
        wait_until(lambda: "Password:" in session.result()["output"])
        session.answer("synthetic-transient-answer")
        monkeypatch.setattr(session, "_terminate", denied)
        with pytest.raises(PermissionError):
            session.close()
        result = session.result()
        assert result["status"] == "failed", "A failed cleanup cannot be reported as cancellation"
        assert "cleanup" in result["message"].lower()
        assert session._answers == [] and session._fd is None
        assert "synthetic-transient-answer" not in session._output
    finally:
        monkeypatch.undo()
        session.close()
