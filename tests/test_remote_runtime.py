from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from autoresearch import remote_runtime as runtime
from autoresearch.store import Store


def test_database_can_live_apart_from_shared_workspaces(tmp_path: Path) -> None:
    artifacts = tmp_path / "shared"
    database = tmp_path / "local"
    store = Store(artifacts, db_dir=database)
    assert store.db_path == database / "research.sqlite3"
    assert store.db_path.is_file()
    assert not (artifacts / "research.sqlite3").exists()
    assert store.run_dir("a" * 12).parent == artifacts / "runs"
    assert Store(artifacts, db_dir=database).list_runs() == []


def test_database_environment_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTORESEARCH_DB_DIR", str(tmp_path / "configured-db"))
    assert Store(tmp_path / "state").db_path.parent == tmp_path / "configured-db"
    assert (
        Store(tmp_path / "state", db_dir=tmp_path / "explicit-db").db_path.parent
        == tmp_path / "explicit-db"
    )


def test_database_cannot_silently_pair_with_a_different_artifact_root(tmp_path: Path) -> None:
    database = tmp_path / "database"
    original = Store(tmp_path / "project-a", db_dir=database)
    with pytest.raises(ValueError, match="different research state directory"):
        Store(tmp_path / "project-b", db_dir=database)
    assert original.list_runs() == []
    assert Store(tmp_path / "project-a", db_dir=database).list_runs() == []


def test_cli_accepts_separate_database_directory(tmp_path: Path) -> None:
    from autoresearch.cli import main

    assert (
        main(["--state-dir", str(tmp_path / "shared"), "--db-dir", str(tmp_path / "db"), "status"])
        == 0
    )
    assert (tmp_path / "db/research.sqlite3").is_file()
    assert not (tmp_path / "shared/research.sqlite3").exists()


def test_network_database_is_rejected_before_controller_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "filesystem_type", lambda path: "nfs4")
    report = runtime.probe(tmp_path)
    assert report["ready"] is False
    assert "persistent host-local" in report["problems"][0]
    with pytest.raises(ValueError, match="nfs4"):
        runtime.start_controller(tmp_path)
    assert not (tmp_path / "controller.json").exists()


def test_descriptor_cannot_redirect_to_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "secret.json"
    outside.write_text("private")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "controller.json").symlink_to(outside)
    with pytest.raises(OSError):
        runtime.controller_status(runtime_dir)
    assert outside.read_text() == "private"


def test_foreign_host_descriptor_never_starts_duplicate(tmp_path: Path) -> None:
    descriptor = {
        "host": "a-different-login-node",
        "pid": os.getpid(),
        "port": 8765,
        "token": "t" * 40,
    }
    runtime._write_descriptor(tmp_path, descriptor)
    assert runtime.controller_status(tmp_path)["status"] == "other_host"
    assert "token" not in runtime.probe(tmp_path)["controller"]
    with pytest.raises(RuntimeError, match="exact host"):
        runtime.start_controller(tmp_path)


def test_unresponsive_live_process_not_replaced(tmp_path: Path) -> None:
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        descriptor = {
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "port": unavailable.getsockname()[1],
            "token": "t" * 40,
        }
        runtime._write_descriptor(tmp_path, descriptor)
        assert runtime.controller_status(tmp_path)["status"] == "unresponsive"
        with pytest.raises(RuntimeError, match="refusing a duplicate"):
            runtime.start_controller(tmp_path)


def _stop_child(directory: Path, descriptor: dict[str, object]) -> None:
    pid = int(str(descriptor["pid"]))
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10
    while (directory / "controller.json").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not (directory / "controller.json").exists(), "controller failed graceful shutdown"


def test_controller_outlives_launcher_reconnects_and_protects_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path.resolve() / "controller"
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    command = [
        sys.executable,
        "-m",
        "autoresearch.remote_runtime",
        "start",
        "--directory",
        str(directory),
    ]
    launched = subprocess.run(command, capture_output=True, text=True, timeout=40)
    assert launched.returncode == 0, launched.stdout + launched.stderr
    descriptor = json.loads(launched.stdout)
    try:
        assert descriptor["status"] == "running"
        assert descriptor["pid"] != os.getpid()
        assert (directory / "controller.json").stat().st_mode & 0o777 == 0o600
        assert (directory / "controller.log").stat().st_mode & 0o777 == 0o600
        url = f"http://127.0.0.1:{descriptor['port']}"
        with httpx.Client(trust_env=False) as client:
            assert client.get(url + "/api/bootstrap").status_code == 401
            headers = {"Authorization": f"Bearer {descriptor['token']}"}
            assert client.get(url + "/api/bootstrap", headers=headers).status_code == 200
            assert client.get(url + "/api/runs", headers=headers).json() == {"runs": []}
        # A second independent launcher reconnects to exactly the same controller.
        reconnected = subprocess.run(command, capture_output=True, text=True, timeout=40)
        assert reconnected.returncode == 0, reconnected.stdout + reconnected.stderr
        assert json.loads(reconnected.stdout)["pid"] == descriptor["pid"]
        with pytest.raises(ValueError, match="different paths"):
            runtime.start_controller(directory, state_dir=tmp_path / "another-state")
    finally:
        _stop_child(directory, descriptor)


def test_stale_descriptor_can_be_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime._write_descriptor(
        tmp_path,
        {
            "host": socket.gethostname(),
            "pid": 12345,
            "port": 8765,
            "token": "t" * 40,
        },
    )
    monkeypatch.setattr(runtime, "_alive", lambda pid: False)
    assert runtime.controller_status(tmp_path)["status"] == "stopped"
