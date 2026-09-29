import asyncio
from pathlib import Path

from textual.widgets import Input, Static

from autoresearch.config import ResearchConfig
from autoresearch.engine import Engine
from autoresearch.store import Store
from autoresearch.tui import ResearchApp


def test_tui_opens_checkpoint_without_starting_research(tmp_path: Path) -> None:
    async def inspect() -> None:
        store = Store(tmp_path)
        run = Engine(store).create("Saved project", "Inspect only", demo=True)
        app = ResearchApp(store, ResearchConfig(), run.id)
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            assert app.run_id == run.id
            assert store.get_run(run.id).stage == run.stage
            assert store.usage(run.id)["calls"] == 0
            assert "Saved project" in str(app.query_one("#status", Static).render())
            assert app.query_one("#note", Input) is not None
    asyncio.run(inspect())
