"""Exercise the public entry point so command registration cannot break startup."""

from pathlib import Path

import pytest

from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.engine import Engine
from autoresearch.store import Store
from autoresearch.tui import ResearchApp


@pytest.mark.parametrize("arguments", [["--help"], ["tui", "--help"], ["status", "--help"]])
def test_cli_help_constructs_all_subcommands(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(arguments)
    assert exit_info.value.code == 0
    assert "usage: metis" in capsys.readouterr().out


def test_tui_cli_launches_current_app_with_configuration_and_saved_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    store = Store(state_dir)
    state = Engine(store).create("Saved run", "Inspect without executing", demo=True)
    config_path = tmp_path / "research.json"
    config = ResearchConfig()
    config.provider.model = "configured-model"
    config_path.write_text(config.model_dump_json())
    launched: list[ResearchApp] = []

    def run(app: ResearchApp) -> None:
        launched.append(app)

    monkeypatch.setattr(ResearchApp, "run", run)
    assert (
        main(
            ["--state-dir", str(state_dir), "tui", "--config", str(config_path), "--run", state.id]
        )
        == 0
    )
    assert len(launched) == 1
    assert launched[0].selected_run == state.id
    assert launched[0].config_path == config_path
    assert launched[0].config.provider.model == "configured-model"
    assert launched[0].store.get_run(state.id).title == "Saved run"
    assert store.usage(state.id)["calls"] == 0


def test_tui_missing_run_is_reported_before_opening_the_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected_launch(app: ResearchApp) -> None:
        pytest.fail("An unknown run must not enter the interactive UI")

    monkeypatch.setattr(ResearchApp, "run", unexpected_launch)
    assert main(["--state-dir", str(tmp_path), "tui", "--run", "missing-run"]) == 1
    assert "run not found" in capsys.readouterr().err


def test_system_commands_inspect_without_creating_or_executing_runs(tmp_path, capsys):
    import json

    assert main(["--state-dir", str(tmp_path), "validate-specs"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert main(["--state-dir", str(tmp_path), "system", "--role", "subset"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["agent"]["handler"] == "coding"
    assert "subset" in report["prompt"].lower()
    assert not (tmp_path / "research.sqlite3").exists()


def test_fidelity_cli_and_evaluation_variants_coexist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    assert main(["--state-dir", str(tmp_path), "fidelity"]) == 0
    assert json.loads(capsys.readouterr().out)["scientific_parity"] is False
    assert main(["--state-dir", str(tmp_path), "evaluate", "variants", str(tmp_path)]) == 0
    variants = json.loads(capsys.readouterr().out)
    assert "configured" in str(variants)
    assert Store(tmp_path).list_runs() == []


class FakeRemoteManager:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.auth_status = "authenticated"
        self.result = {
            "status": "connected",
            "url": "http://127.0.0.1:9001/#remote-token=private-example",
        }

    def hosts(self):
        self.calls.append(("hosts",))
        return ["example-cluster"]

    def profiles(self):
        self.calls.append(("profiles",))
        return [{"name": "cluster", "host": "example-cluster"}]

    def save_profile(self, profile):
        self.calls.append(("save", profile))
        return {"status": "saved", **profile}

    def probe(self, name):
        self.calls.append(("check", name))
        return {"ready": True}

    def install(self, name):
        self.calls.append(("install", name))
        return {"status": "installed"}

    def connect(self, name):
        self.calls.append(("connect", name))
        return self.result

    def status(self, name):
        self.calls.append(("status", name))
        return self.result

    def disconnect(self, name):
        self.calls.append(("disconnect", name))
        return {"status": "disconnected", "message": "Remote research continues."}

    def authenticate(self, name):
        self.calls.append(("login", name))
        return {"status": self.auth_status, "session_id": "auth-1", "output": "Verification code:"}

    def answer_authentication(self, session, answer):
        self.calls.append(("answer", session, answer))
        return {"status": "authenticated", "session_id": session, "output": "Signed in."}

    def cancel_authentication(self, session):
        self.calls.append(("cancel", session))
        return {"status": "cancelled"}

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "action,expected",
    [
        ("hosts", "hosts"),
        ("list", "profiles"),
        ("check", "check"),
        ("install", "install"),
        ("status", "status"),
        ("disconnect", "disconnect"),
    ],
)
def test_remote_cli_dispatch_and_status_never_prints_access_token(
    tmp_path, monkeypatch, capsys, action, expected
):
    manager = FakeRemoteManager()
    monkeypatch.setattr("autoresearch.cli._remote_manager", lambda root: manager)
    command = ["--state-dir", str(tmp_path), "remote", action]
    if action not in {"hosts", "list"}:
        command.append("cluster")
    assert main(command) == 0
    assert any(call[0] == expected for call in manager.calls)
    assert manager.closed
    assert "private-example" not in capsys.readouterr().out


def test_remote_cli_saves_custom_host_and_paths_without_connecting(tmp_path, monkeypatch):
    manager = FakeRemoteManager()
    monkeypatch.setattr("autoresearch.cli._remote_manager", lambda root: manager)
    monkeypatch.setattr("autoresearch.cli._remote_profile", lambda **values: values)
    assert (
        main(
            [
                "--state-dir",
                str(tmp_path),
                "remote",
                "add",
                "cluster",
                "--host",
                "user@cluster.example.org",
                "--port",
                "2222",
                "--remote-db-dir",
                "/local/db",
                "--remote-state-dir",
                "/shared/research",
            ]
        )
        == 0
    )
    saved = manager.calls[0][1]
    assert saved["host"] == "user@cluster.example.org"
    assert saved["port"] == 2222
    assert saved["db_dir"] == "/local/db"
    assert saved["state_dir"] == "/shared/research"
    assert len(manager.calls) == 1


def test_remote_cli_connect_owns_tunnel_until_interrupt_and_opens_only_explicitly(
    tmp_path, monkeypatch, capsys
):
    manager = FakeRemoteManager()
    opened = []
    monkeypatch.setattr("autoresearch.cli._remote_manager", lambda root: manager)
    monkeypatch.setattr("autoresearch.cli.webbrowser.open", lambda url: opened.append(url))

    def interrupt(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr("autoresearch.cli.time.sleep", interrupt)
    assert main(["--state-dir", str(tmp_path), "remote", "connect", "cluster", "--open"]) == 0
    assert opened == [manager.result["url"]]
    assert ("disconnect", "cluster") in manager.calls
    assert manager.closed
    output = capsys.readouterr()
    assert "private-example" in output.out
    assert "Remote research continues" in output.err


def test_remote_cli_login_handles_mfa_without_printing_answer(tmp_path, monkeypatch, capsys):
    manager = FakeRemoteManager()
    manager.auth_status = "authenticating"
    monkeypatch.setattr("autoresearch.cli._remote_manager", lambda root: manager)
    monkeypatch.setattr("autoresearch.cli.getpass.getpass", lambda prompt: "123456-private")
    assert main(["--state-dir", str(tmp_path), "remote", "login", "cluster"]) == 0
    assert ("answer", "auth-1", "123456-private") in manager.calls
    assert manager.closed
    assert "123456-private" not in capsys.readouterr().out


def test_remote_cli_mfa_precedes_install_in_same_session(tmp_path, monkeypatch):
    manager = FakeRemoteManager()
    manager.auth_status = "authenticating"
    monkeypatch.setattr("autoresearch.cli._remote_manager", lambda root: manager)
    monkeypatch.setattr("autoresearch.cli.getpass.getpass", lambda prompt: "verification-response")
    assert main(["--state-dir", str(tmp_path), "remote", "install", "cluster"]) == 0
    assert [call[0] for call in manager.calls] == ["login", "answer", "install"]
    assert manager.closed
