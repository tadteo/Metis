"""Exercise the public entry point so command registration cannot break startup."""

from pathlib import Path

import pytest

from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.engine import Engine
from autoresearch.store import Store
from autoresearch.tui import ResearchApp


@pytest.mark.parametrize(
    "arguments",
    [
        ["--help"],
        ["tui", "--help"],
        ["status", "--help"],
        ["evaluate", "--help"],
        ["fidelity", "--help"],
    ],
)
def test_cli_help_constructs_all_subcommands(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(arguments)
    assert exit_info.value.code == 0
    assert "usage: autoresearch" in capsys.readouterr().out


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
