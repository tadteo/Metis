from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from textual.widgets import Input, TabbedContent

from autoresearch.appearance import load_theme, save_theme
from autoresearch.cli import main
from autoresearch.engine import Engine
from autoresearch.store import Store
from autoresearch.tui import ResearchApp


def test_theme_is_shared_without_mutating_research(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = Store(tmp_path)
    run = Engine(store).create("Synthetic theme fixture", "Check navigation only", demo=True)
    before = store.get_config(run.id).model_dump_json()
    assert main(["--state-dir", str(tmp_path), "theme", "cream"]) == 0
    assert load_theme(Store(tmp_path)) == "cream"
    assert store.get_config(run.id).model_dump_json() == before
    assert store.get_run(run.id).version == run.version
    with pytest.raises(ValueError):
        save_theme(store, "invalid")
    capsys.readouterr()
    assert main(["--state-dir", str(tmp_path), "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == run.id


def test_small_terminal_sections_and_palette_preserve_edits(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path))
        async with app.run_test(size=(80, 24)) as pilot:
            app.action_settings()
            await pilot.pause()
            assert not app.query_one("#actions").display
            field = app.query_one("#setting-0", Input)
            field.value = str(tmp_path / "unsaved-project")
            await pilot.click("#section-model")
            await pilot.pause()
            await pilot.click("#section-project")
            await pilot.pause()
            assert field.value == str(tmp_path / "unsaved-project")
            await pilot.press("ctrl+t")
            assert load_theme(app.store) == "cream"
            await pilot.press("ctrl+k")
            await pilot.pause(0.7)
            assert len(app.screen_stack) == 2
            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one("#details", TabbedContent).active == "settings"
            assert field.value == str(tmp_path / "unsaved-project")
            assert app.store.list_runs() == []
        app.controller.join()

    asyncio.run(scenario())


def test_runs_navigation_moves_focus_out_of_previous_pane(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = Store(tmp_path)
        run = Engine(store).create("Navigation fixture", "Synthetic only", demo=True)
        app = ResearchApp(store)
        async with app.run_test(size=(80, 24)) as pilot:
            app.action_runs()
            await pilot.pause()
            app.action_welcome()
            await pilot.pause()
            assert app.query_one("#details", TabbedContent).active == "welcome"
            app.action_runs()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#details", TabbedContent).active == "overview"
            assert app.selected_run == run.id
            assert store.get_run(run.id).version == run.version
        app.controller.join()

    asyncio.run(scenario())


def test_settings_execution_shortcuts_cannot_start_hidden_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        store = Store(tmp_path)
        Engine(store).create("Hidden execution fixture", "Synthetic only", demo=True)
        app = ResearchApp(store)
        calls: list[object] = []
        monkeypatch.setattr(app.controller, "start", lambda *args, **kwargs: calls.append(args))
        async with app.run_test(size=(80, 24)) as pilot:
            app.action_settings()
            await pilot.pause()
            await pilot.press("ctrl+s", "ctrl+r")
            assert calls == []
            app._navigate("overview")
            await pilot.pause()
            await pilot.press("ctrl+s")
            assert len(calls) == 1
        app.controller.join()

    asyncio.run(scenario())
