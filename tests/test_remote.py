"""Transport contract tests use controlled processes and loopback HTTP only."""

from __future__ import annotations

import base64
import json
import shlex
import stat
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pydantic import ValidationError

import autoresearch.remote as remote
from autoresearch.remote import RemoteError, RemoteManager, RemoteProfile, _Tunnel, ssh_hosts
from autoresearch.runtime_support.process import ProcessResult

TOKEN = "synthetic-browser-token-1234567890"  # noqa: S105 - public test fixture


@pytest.fixture
def manager(tmp_path: Path):
    value = RemoteManager(tmp_path)
    value.save_profile(RemoteProfile(name="cluster", host="researcher@cluster.example", port=2222))
    yield value
    value.close()


def test_profiles_are_private_and_reject_destinations_that_are_ssh_options(
    manager: RemoteManager,
) -> None:
    assert stat.S_IMODE(manager._profile_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(manager.root.stat().st_mode) == 0o700
    assert len(str(manager._socket_root / ("a" * 16))) < 100
    for host in ["-oProxyCommand=bad", "cluster;touch bad", "cluster\nHost *", "user@host $(bad)"]:
        with pytest.raises(ValidationError):
            RemoteProfile(name="test", host=host)
    for host in ["alias", "person@cluster.example", "192.0.2.10", "[2001:db8::1]"]:
        assert RemoteProfile(name="test", host=host).host == host
    with pytest.raises(ValidationError):
        RemoteProfile(name="test", host="host", password="secret")  # noqa: S106 - rejected field
    with pytest.raises(ValidationError):
        RemoteProfile(name="test", host="host", port=65536)
    for python in ["~/venv/bin/python", "python3 -u", "python3; touch bad"]:
        with pytest.raises(ValidationError, match="absolute executable"):
            RemoteProfile(name="test", host="host", python=python)
    assert manager.profiles()[0]["port"] == 2222


def test_config_includes_discover_only_concrete_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ssh = tmp_path / ".ssh"
    (ssh / "parts").mkdir(parents=True)
    (ssh / "config").write_text(
        'Host primary *.internal !excluded\n Include "parts/*.conf"\nHost=direct\n'
    )
    (ssh / "parts/a.conf").write_text("Host compute other\nInclude config\n")
    (ssh / "parts/b.conf").write_text("Host fallback # comment\nHost [wildcard]\n")
    assert ssh_hosts() == ["compute", "direct", "fallback", "other", "primary"]


def test_remote_arguments_are_shell_quoted_without_enabling_forwarding(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = RemoteProfile(
        name="odd",
        host="cluster",
        directory="~/data/a; $(touch leaked) ' space",
        python="/path with space/python3",
        identity_file="/key with space",
    )
    seen: list[list[str]] = []

    def run(argv, **kwargs):
        seen.append(argv)
        return ProcessResult('{"status":"stopped"}', "", 0, 0)

    monkeypatch.setattr(manager, "_run", run)
    manager._helper(profile, "status")
    argv = seen[0]
    assert "ForwardAgent=no" in argv and "ForwardX11=no" in argv
    assert "BatchMode=yes" in argv and "-i" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "StrictHostKeyChecking=ask" in manager._base(profile, batch=False)
    assert not any("StrictHostKeyChecking=no" in argument for argument in argv)
    command = shlex.split(argv[-1])
    assert command[0] == profile.python
    assert json.loads(command[-1])["directory"] == profile.directory
    assert argv[-2] == "cluster"


def test_public_diagnostics_and_profiles_do_not_expose_descriptor_tokens(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manager, "_ensure_master", lambda profile: None)
    monkeypatch.setattr(
        manager,
        "_helper",
        lambda *args: {
            "status": "needs_configuration",
            "ready": False,
            "token": TOKEN,
            "problems": ["database needs local storage " + TOKEN],
            "controller": {"token": TOKEN},
            "slurm": {"ready": False, "secret": TOKEN},
        },
    )
    result = manager.probe("cluster")
    assert result["ready"] is False
    assert "database needs local storage" in result["problems"][0]
    assert TOKEN not in json.dumps(result)
    assert "url" not in json.dumps(manager.profiles())
    assert TOKEN not in manager._profile_path.read_text()


def test_bundle_contains_only_package_files_and_exact_pinned_dependencies(
    manager: RemoteManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "installed" / "autoresearch"
    package.mkdir(parents=True)
    (package / "remote.py").write_text("public code")
    (package / "specs").mkdir()
    (package / "specs/agents.json").write_text("{}")
    (package.parent / "credentials.json").write_text("private material")
    (package / "ignored.pyc").write_bytes(b"cache")
    (package / "credentials.json").write_text("private material")
    (package / ".local.json").write_text("private material")
    (package / "notes.json").write_text("private material")
    monkeypatch.setattr(remote, "__file__", str(package / "remote.py"))
    bundle = json.loads(manager._bundle(manager._profile("cluster")))
    assert sorted(bundle["files"]) == [
        "src/autoresearch/remote.py",
        "src/autoresearch/specs/agents.json",
    ]
    assert base64.b64decode(bundle["files"]["src/autoresearch/remote.py"]) == b"public code"
    import tomllib

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert bundle["requirements"] == project["project"]["dependencies"]


def test_helper_and_install_failure_never_become_ready(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manager, "_ensure_master", lambda profile: None)
    monkeypatch.setattr(
        manager, "_run", lambda *args, **kwargs: ProcessResult("not-json " + TOKEN, TOKEN, 255, 0)
    )
    result = manager.probe("cluster")
    assert result["status"] == "failed" and TOKEN not in json.dumps(result)
    monkeypatch.setattr(manager, "_helper", lambda *args: {"status": "stopped"})
    monkeypatch.setattr(
        manager, "_json_command", lambda *args, **kwargs: {"status": "failed", "message": TOKEN}
    )
    result = manager.install("cluster")
    assert result["status"] == "failed" and TOKEN not in json.dumps(result)


@pytest.mark.parametrize("state", ["running", "other_host", "unresponsive", "error"])
def test_install_refuses_active_or_uncertain_controller(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    monkeypatch.setattr(manager, "_ensure_master", lambda profile: None)
    monkeypatch.setattr(manager, "_helper", lambda *args: {"status": state})
    monkeypatch.setattr(manager, "_bundle", lambda profile: pytest.fail("must not upload"))
    assert manager.install("cluster")["status"] == "failed"


def test_successful_connect_disconnect_cancels_only_forwarding(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    operations: list[str] = []
    monkeypatch.setattr(manager, "_ensure_master", lambda profile: None)
    monkeypatch.setattr(
        manager, "_helper", lambda *args: {"status": "running", "port": 8765, "token": TOKEN}
    )
    monkeypatch.setattr(
        manager, "_forward", lambda tunnel, operation: operations.append(operation) or True
    )
    monkeypatch.setattr(manager, "_healthy", lambda tunnel: True)
    result = manager.connect("cluster")
    assert result["status"] == "connected"
    assert result["url"].endswith("#remote-token=" + TOKEN)
    assert result["local_port"] != 8765
    assert manager.connect("cluster")["url"] == result["url"]
    assert manager.disconnect("cluster")["status"] == "disconnected"
    assert operations == ["forward", "cancel"]
    assert TOKEN not in json.dumps(manager.status("cluster"))


def test_tunnel_is_not_ready_until_authenticated_http_response(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(remote, "_READY_TIMEOUT", 0.01)
    monkeypatch.setattr(manager, "_ensure_master", lambda profile: None)
    monkeypatch.setattr(
        manager, "_helper", lambda *args: {"status": "running", "port": 8765, "token": TOKEN}
    )
    operations: list[str] = []
    monkeypatch.setattr(
        manager, "_forward", lambda tunnel, operation: operations.append(operation) or True
    )
    monkeypatch.setattr(manager, "_healthy", lambda tunnel: False)
    result = manager.connect("cluster")
    assert result["status"] == "failed" and "url" not in result
    assert operations == ["forward", "cancel"]


def test_health_uses_bearer_authentication_and_no_environment_proxy(manager: RemoteManager) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            correct = self.headers.get("Authorization") == "Bearer " + TOKEN
            self.send_response(200 if correct else 401)
            self.end_headers()
            self.wfile.write(b'{"status":"running"}')

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    try:
        tunnel = _Tunnel(manager._profile("cluster"), server.server_port, token=TOKEN)
        assert manager._healthy(tunnel)
        tunnel.token = "wrong"  # noqa: S105 - deliberately incorrect fixture
        assert not manager._healthy(tunnel)
    finally:
        server.shutdown()
        worker.join()
        server.server_close()


def test_reconnect_is_bounded_and_disconnect_prevents_late_forward(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(remote, "_MONITOR_INTERVAL", 0.001)
    monkeypatch.setattr(remote, "_RECONNECT_DELAYS", (0.001, 0.001, 0.001))
    tunnel = _Tunnel(manager._profile("cluster"), 12345, token=TOKEN, status="connected")
    monkeypatch.setattr(manager, "_healthy", lambda tunnel: False)
    monkeypatch.setattr(manager, "_forward", lambda *args: True)
    attempts: list[str] = []

    def establish(tunnel):
        attempts.append("attempt")
        raise RemoteError("Unavailable")

    monkeypatch.setattr(manager, "_establish", establish)
    manager._monitor(tunnel)
    assert attempts == ["attempt"] * 3
    assert tunnel.status == "failed" and tunnel.token == ""
    # A blocked start returning after disconnect must never install a forward.
    monkeypatch.undo()
    monkeypatch.setattr(manager, "_ensure_master", lambda profile: None)

    def helper(*args):
        tunnel.stop.set()
        return {"status": "running", "port": 8765, "token": TOKEN}

    monkeypatch.setattr(manager, "_helper", helper)
    monkeypatch.setattr(manager, "_forward", lambda *args: pytest.fail("late forward"))
    with pytest.raises(RemoteError, match="disconnected"):
        manager._establish(tunnel)


def test_transport_timeout_and_close_reap_local_children(manager: RemoteManager) -> None:
    result = manager._run([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.05)
    assert result.timed_out and not manager._children
    started = threading.Event()

    def operation():
        started.set()
        manager._run([sys.executable, "-c", "import time; time.sleep(60)"], timeout=60)

    thread = threading.Thread(target=operation)
    thread.start()
    assert started.wait(1)
    deadline = time.monotonic() + 2
    while not manager._children and time.monotonic() < deadline:
        time.sleep(0.01)
    manager.close()
    thread.join(timeout=3)
    assert not thread.is_alive() and not manager._children


def test_manager_authentication_api_reuses_owned_master_for_commands(
    manager: RemoteManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "ssh"
    fake.write_text(
        "#!" + sys.executable + "\n"
        "import sys, time\n"
        "from pathlib import Path\n"
        "args=sys.argv[1:]\n"
        "control=Path(args[args.index('-S')+1]) if '-S' in args else None\n"
        "if '-O' in args:\n"
        " raise SystemExit(0 if control and control.exists() else 255)\n"
        "if 'ControlMaster=yes' in args:\n"
        " print('Verification code:',end='',flush=True)\n"
        " assert input() == '654321'\n"
        " control.write_text('ready')\n"
        " time.sleep(60)\n"
        "else:\n"
        " assert control and control.exists()\n"
        ' print(\'{"status":"ready","ready":true}\')\n'
    )
    fake.chmod(0o700)
    original = manager._base

    def base(profile, **kwargs):
        return [str(fake), *original(profile, **kwargs)[1:]]

    monkeypatch.setattr(manager, "_base", base)
    auth = manager.authenticate("cluster")
    deadline = time.monotonic() + 5
    while "Verification code" not in manager.authentication(auth["session_id"])["output"]:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    manager.answer_authentication(auth["session_id"], "654321")
    while manager.authentication(auth["session_id"])["status"] != "authenticated":
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert manager.probe("cluster")["status"] == "ready"
    assert "654321" not in manager._profile_path.read_text()
    assert "654321" not in manager.authentication(auth["session_id"])["output"]
    assert manager.cancel_authentication(auth["session_id"])["status"] == "cancelled"


def test_existing_user_master_is_borrowed_and_never_exited(
    manager: RemoteManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def run(argv, **kwargs):
        commands.append(argv)
        return ProcessResult("", "", 0, 0)

    monkeypatch.setattr(manager, "_run", run)
    result = manager.authenticate("cluster")
    assert result["status"] == "authenticated"
    session = manager._session_for("cluster")
    assert session is not None and session.borrowed
    manager.close()
    assert all("exit" not in argv for argv in commands)
