"""Real PTYs exercise authentication without an SSH server or network connection."""

import json
import sys
import time
from pathlib import Path

import pytest

from autoresearch.ssh_auth import AuthenticationSession


def wait_for(session: AuthenticationSession, predicate, timeout: float = 5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = session.result()
        if predicate(result):
            return result
        time.sleep(0.02)
    pytest.fail("Authentication did not reach the expected state")


def test_host_trust_password_and_mfa_stay_inside_pty(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    script = tmp_path / "fake_ssh.py"
    script.write_text(
        "import os, sys, termios, time\n"
        "from pathlib import Path\n"
        "assert os.isatty(0)\n"
        "assert not termios.tcgetattr(0)[3] & termios.ECHO\n"
        "for prompt, expected in [('Host key: type yes: ', 'yes'), ('Password: ', 'private-password'), ('Verification code: ', '735921')]:\n"
        " print(prompt, end='', flush=True)\n"
        " assert input() == expected\n"
        "print('Echo attempt: private-password and 735921', flush=True)\n"
        "Path(sys.argv[1]).write_text('ready')\n"
        "time.sleep(60)\n"
    )
    session = AuthenticationSession([sys.executable, str(script), str(ready)], ready.exists)
    try:
        for prompt, answer in [
            ("Host key", "yes"),
            ("Password:", "private-password"),
            ("Verification code", "735921"),
        ]:
            wait_for(session, lambda result, prompt=prompt: prompt in result["output"])
            session.answer(answer)
        result = wait_for(session, lambda result: result["status"] == "authenticated")
        assert "private-password" not in json.dumps(result)
        assert "735921" not in json.dumps(result)
        assert session._answers == []
        assert session._process is not None and session._process.poll() is None
        assert sorted(path.name for path in tmp_path.iterdir()) == ["fake_ssh.py", "ready"]
    finally:
        session.close()
    assert session._process is not None and session._process.poll() is not None


def test_cancel_and_timeout_reap_authentication_process(tmp_path: Path) -> None:
    session = AuthenticationSession(
        [sys.executable, "-c", "import time; print('Password:',flush=True); time.sleep(60)"],
        lambda: False,
        timeout=0.25,
    )
    try:
        result = wait_for(session, lambda result: result["status"] == "expired")
        assert result["status"] == "expired"
        wait_for(
            session,
            lambda result: session._process is not None and session._process.poll() is not None,
        )
    finally:
        session.close()
    other = AuthenticationSession(
        [sys.executable, "-c", "import time; time.sleep(60)"], lambda: False
    )
    assert other.close()["status"] == "cancelled"
    assert other._process is not None and other._process.poll() is not None


@pytest.mark.parametrize("answer", ["one\ntwo", "one\rtwo", "one\x00two", "\x03", "a" * 4097])
def test_answer_cannot_inject_extra_responses(answer: str) -> None:
    session = AuthenticationSession([], lambda: True, borrowed=True)
    try:
        with pytest.raises(ValueError, match="one line"):
            session.answer(answer)
    finally:
        session.close()


def test_failure_is_not_authentication_and_borrowed_master_is_not_killed() -> None:
    session = AuthenticationSession([sys.executable, "-c", "raise SystemExit(255)"], lambda: False)
    try:
        assert wait_for(session, lambda result: result["status"] == "failed")["status"] == "failed"
    finally:
        session.close()
    borrowed = AuthenticationSession([], lambda: True, borrowed=True)
    assert borrowed.result()["status"] == "authenticated"
    assert borrowed._process is None
    borrowed.close()


def test_partial_and_ansi_echo_are_redacted_before_display() -> None:
    session = AuthenticationSession([], lambda: True, borrowed=True)
    session._answers = ["secret-value"]
    session._output = "Password: secret-\x1b[31mvalue\x1b[0m\nsec"
    result = session.result()
    assert "secret" not in result["output"]
    assert not result["output"].endswith("sec")
    session.close()
