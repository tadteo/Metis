"""Exercise the transferred bootstrap, with only package downloads substituted."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from autoresearch.remote import _INSTALL, _REQUIREMENTS


def payload(root: Path) -> dict[str, Any]:
    source = b'"""Public application fixture."""\n'
    name = "src/autoresearch/__init__.py"
    digest = hashlib.sha256(json.dumps(_REQUIREMENTS).encode())
    digest.update(name.encode() + b"\0" + source)
    return {
        "directory": str(root),
        "requirements": _REQUIREMENTS,
        "sha256": digest.hexdigest(),
        "files": {name: base64.b64encode(source).decode()},
    }


def execute_bootstrap(request: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    try:
        exec(compile(_INSTALL, "remote-bootstrap", "exec"), {})  # noqa: S102 — own trusted bootstrap
    except SystemExit as error:
        assert error.code == 0


def test_transferred_bootstrap_writes_valid_installable_package_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve() / "a directory with spaces; literal$(text)"
    request = payload(root)
    calls: list[list[str]] = []

    def provision(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs.get("shell") is not True
        calls.append(argv)
        if argv[1:3] == ["-m", "venv"]:
            python = Path(argv[-1]) / "bin/python"
            python.parent.mkdir(parents=True)
            python.write_text("fixture interpreter")
        else:
            assert argv[1:4] == ["-m", "pip", "install"]
            package = Path(argv[-1])
            metadata = tomllib.loads((package / "pyproject.toml").read_text())
            assert metadata["project"]["dependencies"] == _REQUIREMENTS
            assert metadata["project"]["name"] == "metis-research"
            assert metadata["project"]["scripts"]["metis"] == "autoresearch.cli:main"
            assert metadata["project"]["scripts"]["autoresearch"] == "autoresearch.cli:main"
            assert (package / "src/autoresearch/__init__.py").read_text().startswith('"""Public')
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", provision)
    execute_bootstrap(request, monkeypatch)
    assert json.loads(capsys.readouterr().out)["status"] == "installed"
    assert json.loads((root / "installed.json").read_text())["sha256"] == request["sha256"]
    assert (root / "installed.json").stat().st_mode & 0o777 == 0o600
    assert len(calls) == 2
    execute_bootstrap(request, monkeypatch)
    assert json.loads(capsys.readouterr().out)["status"] == "installed"
    assert len(calls) == 2


def test_bootstrap_failure_does_not_claim_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve() / "runtime"

    def failed(argv: list[str], **kwargs: Any) -> None:
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        execute_bootstrap(payload(root), monkeypatch)
    assert not (root / "installed.json").exists()


def test_bootstrap_rejects_redirected_installation_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    outside = root / "outside"
    outside.mkdir()
    (root / "redirect").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        execute_bootstrap(payload(root / "redirect" / "runtime"), monkeypatch)
    assert list(outside.iterdir()) == []


def test_bootstrap_cannot_mutate_a_running_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve() / "runtime"
    root.mkdir()
    with (root / "controller.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        execute_bootstrap(payload(root), monkeypatch)
        assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert not (root / "venv").exists()
    assert not (root / "installed.json").exists()
