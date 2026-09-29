from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Collapsible, Input, OptionList, Static, TabbedContent, TextArea

from autoresearch.appearance import PALETTES
from autoresearch.contracts import ExperimentResult
from autoresearch.engine import Engine
from autoresearch.store import Store
from autoresearch.tui import ResearchApp


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_question_and_visible_navigation_do_not_start_research(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path))
        async with app.run_test(size=size) as pilot:
            assert app.query_one("#navigation").display == (size[0] >= 110)
            app.query_one("#home-question", TextArea).load_text("How can we test this assumption?")
            assert await pilot.click("#begin-inquiry")
            await pilot.pause()
            assert app.query_one("#details", TabbedContent).active == "new"
            assert (
                app.query_one("#new-objective", TextArea).text == "How can we test this assumption?"
            )
            assert app.store.list_runs() == []
            prefix = "nav" if size[0] >= 110 else "compact"
            assert await pilot.click(f"#{prefix}-settings")
            await pilot.pause()
            assert app.query_one("#details", TabbedContent).active == "settings"
            app.query_one("#setting-0", Input).value = str(tmp_path / "research")
            assert await pilot.click("#section-model")
            await pilot.pause()
            assert app._settings_section == "model"
            assert await pilot.click("#section-back")
            await pilot.pause()
            assert app._settings_section == "data"
            assert await pilot.click("#section-project")
            await pilot.pause()
            assert app.query_one("#setting-0", Input).value == str(tmp_path / "research")
            assert app.store.list_runs() == []
        app.controller.join()

    asyncio.run(scenario())


def test_readable_evidence_keeps_full_receipts_and_research_tabs(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = Store(tmp_path)
        state = Engine(store).create("Synthetic inquiry", "An uncertain question", demo=True)
        state.experiments = [
            ExperimentResult(
                id="negative-result",
                status="failed",
                metrics={"score": 0.2},
                stdout="Measured output",
                stderr="[bold]Diagnostic evidence[/bold]",
            )
        ]
        store.save(state)
        app = ResearchApp(store, run_id=state.id)
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.query_one("#recent-runs", OptionList).option_count == 1
            assert await pilot.click("#view-experiments-tab")
            await pilot.pause()
            assert app.query_one("#details", TabbedContent).active == "experiments-tab"
            assert "0.2" in str(app.query_one("#experiment-reading", Static).render())
            assert "Diagnostic evidence" in app.query_one("#experiment-detail", TextArea).text
            receipt = app.query_one("#experiment-detail").ancestors
            assert any(isinstance(parent, Collapsible) and parent.collapsed for parent in receipt)
            assert store.get_run(state.id).version == state.version
            assert await pilot.click("#view-overview")
            await pilot.pause()
            assert "An uncertain question" in str(
                app.query_one("#overview-question", Static).render()
            )
            assert app.query_one("#run", Button).display
        app.controller.join()

    asyncio.run(scenario())


def test_requested_palette_is_shared_by_css() -> None:
    css = (Path(__file__).parents[1] / "src/autoresearch/static/style.css").read_text()
    assert PALETTES["cream"]["bg"] == "#F3EBDD"
    assert PALETTES["charcoal"]["bg"] == "#1D1C1A"
    for palette in PALETTES.values():
        for name, value in palette.items():
            assert f"--{name.replace('_', '-')}: {value};" in css


def test_compact_complete_records_are_reachable(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = Store(tmp_path)
        state = Engine(store).create("Saved project", "Read the complete evidence", demo=True)
        app = ResearchApp(store, run_id=state.id)
        async with app.run_test(size=(80, 24)) as pilot:
            for view in ("overview", "experiments-tab", "activity"):
                app._navigate(view)
                await pilot.pause()
                pane = app.query_one(f"#{view}")
                receipt = pane.query_one(Collapsible)
                receipt.scroll_visible(animate=False)
                await pilot.pause()
                assert await pilot.click(receipt.query_one("CollapsibleTitle"))
                await pilot.pause()
                assert not receipt.collapsed
                raw = receipt.query_one(TextArea)
                raw.focus()
                await pilot.pause()
                reading = pane.query_one(".reading")
                assert reading.allow_vertical_scroll
                reading.scroll_end(animate=False)
                await pilot.pause()
                assert raw.region.bottom <= reading.region.bottom
                assert raw.region.bottom > reading.region.y
        app.controller.join()

    asyncio.run(scenario())
