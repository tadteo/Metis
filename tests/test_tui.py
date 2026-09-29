import asyncio
from pathlib import Path

from textual.widgets import Input, Select, Static, TextArea

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
            system = app.query_one("#text-system", TextArea).text
            assert "WORKFLOW" in system and "meta_refine" in system
            assert "coding_step" in system and "Prompt" in system
            assert "guards:" in system and "Limits:" in system
            app.query_one("#system-agent", Select).value = "limitations"
            await pilot.pause()
            assert "Do not fabricate" in app.query_one("#text-instructions", TextArea).text

    asyncio.run(inspect())


def test_corrupt_behavior_bundle_keeps_other_diagnostic_views_available(tmp_path: Path) -> None:
    async def inspect() -> None:
        store = Store(tmp_path)
        run = Engine(store).create("Damaged archive", "Retain diagnostics", demo=True)
        artifact = next(a for a in store.artifacts(run.id) if a["kind"] == "ai_behavior")
        (store.run_dir(run.id) / artifact["path"]).write_text("{}")
        app = ResearchApp(store, ResearchConfig(), run.id)
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            assert "untrusted" in app.query_one("#text-system", TextArea).text
            assert "artifact" in app.query_one("#text-system", TextArea).text.lower()
            assert "limitations" in app.query_one("#text-state", TextArea).text
            assert "ai_behavior" in app.query_one("#text-artifacts", TextArea).text
            assert store.usage(run.id)["calls"] == 0

    asyncio.run(inspect())
