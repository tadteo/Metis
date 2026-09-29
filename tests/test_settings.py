"""Setup saves private defaults, never work, and survives interface restarts."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from textual.widgets import Input, TabbedContent, TextArea

from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.engine import Engine
from autoresearch.settings import FIELDS, load_settings, save_settings, validate_settings
from autoresearch.store import ConflictError, Store
from autoresearch.tui import ResearchApp


def test_settings_persist_without_changing_existing_run_and_conflicts_fail(tmp_path: Path) -> None:
    store = Store(tmp_path)
    run = Engine(store).create("Saved run", "Recorded configuration", demo=True)
    before = store.get_config(run.id)
    config, revision = load_settings(store)
    config.provider.model = "configured-later"
    config.privacy.cache = False
    assert save_settings(store, config, revision) == 1
    assert load_settings(Store(tmp_path))[0] == config
    assert store.get_config(run.id) == before
    assert store.usage(run.id)["calls"] == 0
    with pytest.raises(ConflictError, match="another interface"):
        save_settings(store, ResearchConfig(), revision)
    assert load_settings(store)[0] == config


def test_invalid_settings_and_literal_credentials_do_not_replace_defaults(tmp_path: Path) -> None:
    store = Store(tmp_path)
    config, revision = load_settings(store)
    config.provider.api_key_env = "invalid credential value"
    with pytest.raises(ValueError, match="environment variable"):
        save_settings(store, config, revision)
    config = ResearchConfig()
    with pytest.raises(ValueError):
        validate_settings({"budget": {"usd": -1}})
    assert load_settings(store) == (ResearchConfig(), 0)
    data = ResearchConfig().model_dump(mode="json")
    data["role_providers"] = {"novelty": {"api_key_env": "bad variable"}}
    with pytest.raises(ValueError, match="environment variable"):
        validate_settings(data)


def test_cli_welcome_noninteractive_setup_and_settings_edit(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    prefix = ["--state-dir", str(tmp_path)]
    assert main(prefix) == 0
    assert "Metis welcomes you." in capsys.readouterr().out
    assert not (tmp_path / "research.sqlite3").exists()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(prefix + ["setup"]) == 2
    assert "settings import" in capsys.readouterr().err
    assert main(prefix + ["settings", "set", "provider.model", '"saved-model"']) == 0
    assert main(prefix + ["settings", "show"]) == 0
    assert '"saved-model"' in capsys.readouterr().out
    assert main(prefix + ["settings", "set", "budget.usd", "-1"]) == 1
    assert load_settings(Store(tmp_path))[0].budget.usd == 25
    assert Store(tmp_path).list_runs() == []


def test_cli_wizard_saves_partial_setup_and_cancel_is_atomic(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        "autoresearch.setup_cli.preflight",
        lambda *a, **k: {
            "ready": False,
            "checks": [{"status": "error", "name": "source", "message": "Choose source"}],
        },
    )
    answers = iter([""] * len(FIELDS) + ["y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["--state-dir", str(tmp_path), "setup"]) == 0
    assert load_settings(Store(tmp_path))[1] == 1
    assert "Setup is incomplete" in capsys.readouterr().out
    answers = iter([""] * len(FIELDS) + ["n"])
    assert main(["--state-dir", str(tmp_path), "setup"]) == 0
    assert load_settings(Store(tmp_path))[1] == 1
    assert Store(tmp_path).list_runs() == []


@pytest.mark.parametrize("size", [(110, 40), (80, 24)])
def test_tui_first_run_settings_save_reload_and_new_run_defaults(tmp_path: Path, size) -> None:
    async def scenario() -> None:
        store = Store(tmp_path)
        app = ResearchApp(store)
        async with app.run_test(size=size) as pilot:
            assert app.query_one("#details", TabbedContent).active == "welcome"
            assert not store.list_runs()
            app.action_settings()
            model_index = next(i for i, f in enumerate(FIELDS) if f.path == "provider.model")
            app.query_one(f"#setting-{model_index}", Input).value = "my-saved-model"
            button = app.query_one("#settings-save")
            button.scroll_visible(animate=False)
            await pilot.pause()
            assert await pilot.click("#settings-save")
            await pilot.pause()
            assert load_settings(store)[0].provider.model == "my-saved-model"
            assert app._configuration("").provider.model == "my-saved-model"
            assert not store.list_runs()
            # Unapplied advanced edits are never silently replaced by a form save.
            app.query_one("#settings-json", TextArea).load_text('{"mode": "live"}')
            with pytest.raises(ValueError, match="unapplied"):
                app._settings_form()
        app.controller.join()
        reopened = ResearchApp(Store(tmp_path))
        assert reopened.config.provider.model == "my-saved-model"

    asyncio.run(scenario())


def test_saved_defaults_are_used_by_cli_and_explicit_file_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    store = Store(tmp_path / "state")
    config, revision = load_settings(store)
    config.provider.model = "shared-default"
    save_settings(store, config, revision)
    launched = []
    monkeypatch.setattr(ResearchApp, "run", lambda app: launched.append(app.config.provider.model))
    assert main(["--state-dir", str(store.root), "tui"]) == 0
    override = tmp_path / "override.json"
    override.write_text(json.dumps({"provider": {"model": "explicit-file"}}))
    assert main(["--state-dir", str(store.root), "tui", "--config", str(override)]) == 0
    assert launched == ["shared-default", "explicit-file"]
