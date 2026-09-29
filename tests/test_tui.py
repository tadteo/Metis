from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent, TextArea

from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.contracts import ExperimentResult, ExperimentSpec, RunState, Stage
from autoresearch.engine import Engine
from autoresearch.store import Store
from autoresearch.tui import ResearchApp, display


async def settle(app: ResearchApp, pilot: Pilot[None]) -> None:
    for _ in range(100):
        await pilot.pause(0.02)
        if not app.controller.busy():
            app.refresh_state()
            await pilot.pause()
            return
    raise AssertionError("The background operation did not finish")


async def click_visible(app: ResearchApp, pilot: Pilot[None], selector: str) -> None:
    app.query_one(selector, Button).scroll_visible(animate=False)
    await pilot.pause()
    assert await pilot.click(selector)


def test_create_demo_step_inspect_activity_and_pause(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path))
        async with app.run_test(size=(110, 40)) as pilot:
            assert app.query_one("#details", TabbedContent).active == "new"
            app.query_one("#new-title", Input).value = "Terminal experiment"
            app.query_one("#new-objective", TextArea).load_text("Evaluate the synthetic benchmark.")
            await click_visible(app, pilot, "#create-demo")
            await settle(app, pilot)
            assert app.selected_run is not None
            run_id = app.selected_run
            assert app.store.get_config(run_id).mode == "demo"
            assert app.store.usage(run_id)["calls"] == 0
            assert app.query_one("#runs", DataTable).row_count == 1
            assert (
                "Evaluate the synthetic benchmark" in app.query_one("#overview-text", TextArea).text
            )
            await pilot.press("ctrl+s")
            await settle(app, pilot)
            assert app.store.get_run(run_id).version >= 2
            assert app.store.usage(run_id)["calls"] > 0
            assert app.query_one("#events", DataTable).row_count > 1
            app.query_one("#details", TabbedContent).active = "activity"
            table = app.query_one("#events", DataTable)
            table.focus()
            table.move_cursor(row=table.row_count - 1)
            await pilot.press("enter")
            assert '"kind"' in app.query_one("#event-detail", TextArea).text
            await pilot.press("ctrl+p")
            assert app.store.is_paused(run_id)
            assert "Pause requested" in str(app.query_one("#notice", Static).render())
        app.controller.join()

    asyncio.run(scenario())


def test_persistent_history_and_actual_experiment_and_manuscript(tmp_path: Path) -> None:
    store = Store(tmp_path)
    older = Engine(store).create("Older research", "Actual persisted objective", demo=True)
    older.experiments = [
        ExperimentResult(
            id="measured-1",
            status="completed",
            metrics={"score": 0.825},
            stdout="Training completed",
            stderr="diagnostic detail",
        )
    ]
    older.manuscript = "# Measured result\nThe score was 0.825."
    store.save(older)
    Engine(store).create("Recent research", "Another objective", demo=True)

    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path), run_id=older.id)
        async with app.run_test(size=(100, 35)) as pilot:
            assert app.query_one("#runs", DataTable).row_count == 2
            assert app.selected_run == older.id
            assert "0.825" in app.query_one("#experiment-detail", TextArea).text
            assert "Training completed" in app.query_one("#experiment-detail", TextArea).text
            assert "diagnostic detail" in app.query_one("#experiment-detail", TextArea).text
            assert app.query_one("#manuscript", TextArea).text == older.manuscript
            table = app.query_one("#runs", DataTable)
            table.focus()
            table.move_cursor(row=0)
            await pilot.press("enter")
            assert app.selected_run != older.id
            assert "Another objective" in app.query_one("#overview-text", TextArea).text
        app.controller.join()

    asyncio.run(scenario())


def test_live_creation_is_explicit_and_failed_setup_does_not_create_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "research.json"
    config_path.write_text('{"mode":"demo"}')
    observed: list[str] = []

    def check(config: Any, **kwargs: Any) -> dict[str, Any]:
        observed.append(config.mode)
        return {
            "ready": False,
            "checks": [
                {"name": "provider", "status": "error", "message": "Set the configured API key"}
            ],
        }

    monkeypatch.setattr("autoresearch.setup.preflight", check)

    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path / "runtime"), config_path=config_path)
        async with app.run_test(size=(110, 40)) as pilot:
            await click_visible(app, pilot, "#check-setup")
            await settle(app, pilot)
            assert "SETUP NEEDS ATTENTION" in app.query_one("#setup-result", TextArea).text
            await click_visible(app, pilot, "#create-live")
            await settle(app, pilot)
            assert observed == ["live", "live"]
            assert app.store.list_runs() == []
            assert "configured API key" in app.query_one("#setup-result", TextArea).text
        app.controller.join()

    asyncio.run(scenario())


def test_intervention_and_budget_controls_update_persisted_run(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Controls", "Human guidance", demo=True)

    async def scenario() -> None:
        app = ResearchApp(store, run_id=state.id)
        async with app.run_test(size=(110, 42)) as pilot:
            app.query_one("#details", TabbedContent).active = "controls"
            app.query_one("#intervention", TextArea).load_text(
                "Measure the error bars before promotion."
            )
            await click_visible(app, pilot, "#intervene")
            await settle(app, pilot)
            assert store.get_run(state.id).feedback == "Measure the error bars before promotion."
            app.query_one("#budget-usd", Input).value = "42.5"
            app.query_one("#budget-calls", Input).value = "2500"
            await click_visible(app, pilot, "#save-budget")
            await settle(app, pilot)
            assert store.get_config(state.id).budget.usd == 42.5
            assert store.get_config(state.id).budget.max_calls == 2500
            assert store.usage(state.id)["calls"] == 0
        app.controller.join()

    asyncio.run(scenario())


def test_ui_stays_responsive_and_exit_waits_for_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Background", "Safe exit", demo=True)
    entered, release = threading.Event(), threading.Event()

    def slow_run(self: Engine, run_id: str, max_steps: int | None = None) -> RunState:
        with self.store.lease(run_id):
            entered.set()
            assert release.wait(5)
            current = self.store.get_run(run_id)
            current.status = "paused" if self.store.is_paused(run_id) else "ready"
            self.store.save(current)
            return current

    monkeypatch.setattr(Engine, "run", slow_run)

    async def scenario() -> None:
        app = ResearchApp(store, run_id=state.id)
        try:
            async with app.run_test(size=(100, 35)) as pilot:
                await pilot.press("ctrl+r")
                for _ in range(30):
                    if entered.is_set():
                        break
                    await pilot.pause(0.02)
                assert entered.is_set()
                await pilot.press("ctrl+n")
                assert app.query_one("#details", TabbedContent).active == "new"
                assert app.controller.busy(state.id)
                await pilot.press("ctrl+q")
                assert store.is_paused(state.id)
                assert app.controller.busy(state.id)
                assert app.is_running
                assert "Finishing active checkpoints" in str(
                    app.query_one("#notice", Static).render()
                )
                release.set()
                for _ in range(40):
                    await pilot.pause(0.03)
                    if not app.is_running:
                        break
                assert not app.controller.busy()
                assert store.get_run(state.id).status == "paused"
        finally:
            release.set()
            app.controller.join()

    asyncio.run(scenario())


def test_terminal_run_controls_disabled_and_small_screen_support(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Finished", "No extra paid work", demo=True)
    state.stage, state.status = Stage.COMPLETE, "completed"
    store.save(state)

    async def scenario() -> None:
        app = ResearchApp(store, run_id=state.id)
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.query_one("#run", Button).disabled
            assert app.query_one("#step", Button).disabled
            await pilot.press("ctrl+r")
            assert not app.controller.busy()
            await pilot.press("ctrl+n")
            assert app.query_one("#new-title", Input).has_focus
            await click_visible(app, pilot, "#create-demo")
            await settle(app, pilot)
            assert len(store.list_runs()) == 2
        app.controller.join()

    asyncio.run(scenario())


def test_check_cli_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.json"
    config.write_text("{}")
    monkeypatch.setattr(
        "autoresearch.setup.preflight", lambda *args, **kwargs: {"ready": False, "checks": []}
    )
    assert main(["check", "--config", str(config)]) == 2
    assert json.loads(capsys.readouterr().out)["ready"] is False


def test_terminal_output_redacts_secrets_and_strips_control_sequences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "synthetic-sensitive-fixture")
    value = display({"message": "synthetic-sensitive-fixture\x1b]52;clipboard\x07"})
    assert "synthetic-sensitive-fixture" not in value
    assert "\x1b" not in value and "\x07" not in value


def test_live_creation_snapshots_source_without_starting_paid_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "project"
    source.mkdir()
    (source / "train.py").write_text("print('operator source')")
    config = tmp_path / "live.json"
    config.write_text(json.dumps({"mode": "demo", "project": {"source_dir": str(source)}}))
    monkeypatch.setattr(
        "autoresearch.setup.preflight", lambda *args, **kwargs: {"ready": True, "checks": []}
    )

    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path / "runtime"), config_path=config)
        async with app.run_test(size=(110, 40)) as pilot:
            app.query_one("#new-title", Input).value = "Live project"
            app.query_one("#new-objective", TextArea).load_text("Measure a real baseline.")
            await click_visible(app, pilot, "#create-live")
            await settle(app, pilot)
            assert app.selected_run
            assert app.store.get_config(app.selected_run).mode == "live"
            assert app.store.usage(app.selected_run)["calls"] == 0
            assert (
                app.store.run_dir(app.selected_run) / "source/train.py"
            ).read_text() == "print('operator source')"
        app.controller.join()

    asyncio.run(scenario())


def test_pending_experiment_and_slurm_logs_are_visible(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Pending experiment", "Inspect running work", demo=True)
    workspace = store.run_dir(state.id) / "experiments" / "pending-1"
    workspace.mkdir(parents=True)
    (workspace / ".autoresearch-stdout.log").write_text("Epoch 3: measured loss 0.41")
    state.pending_experiment = ExperimentSpec(
        id="pending-1", kind="subset", workspace=str(workspace), argv=["python3", "train.py"]
    )
    state.pending_job_id, state.status = "12345", "waiting"
    store.save(state)

    async def scenario() -> None:
        app = ResearchApp(store, run_id=state.id)
        async with app.run_test(size=(110, 40)) as pilot:
            assert app.query_one("#experiments", DataTable).row_count == 1
            app.query_one("#details", TabbedContent).active = "experiments-tab"
            await pilot.pause()
            table = app.query_one("#experiments", DataTable)
            table.focus()
            await pilot.press("enter")
            detail = app.query_one("#experiment-detail", TextArea).text
            assert "12345" in detail and "Epoch 3" in detail
            assert '"status": "scheduler pending"' in detail
        app.controller.join()

    asyncio.run(scenario())


def test_pause_during_startup_is_not_lost_to_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Startup pause", "Avoid unintended work", demo=True)
    entered, release = threading.Event(), threading.Event()
    original_resume = Engine.resume

    def delayed_resume(self: Engine, run_id: str) -> RunState:
        entered.set()
        assert release.wait(5)
        return original_resume(self, run_id)

    monkeypatch.setattr(Engine, "resume", delayed_resume)

    async def scenario() -> None:
        app = ResearchApp(store, run_id=state.id)
        try:
            async with app.run_test(size=(100, 35)) as pilot:
                await pilot.press("ctrl+r")
                for _ in range(30):
                    if entered.is_set():
                        break
                    await pilot.pause(0.02)
                assert entered.is_set()
                await pilot.press("ctrl+p")
                release.set()
                await settle(app, pilot)
                assert store.is_paused(state.id)
                assert store.get_run(state.id).status == "paused"
                assert store.usage(state.id)["calls"] == 0
        finally:
            release.set()
            app.controller.join()

    asyncio.run(scenario())


def test_saved_run_routing_cost_fidelity_and_artifacts_are_inspectable_without_execution(
    tmp_path: Path,
) -> None:
    from autoresearch.accounting import SubordinateCall
    from autoresearch.config import ResearchConfig
    from autoresearch.contracts import ProviderConfig, Usage

    store = Store(tmp_path)
    config = ResearchConfig(
        mode="demo",
        role_providers={"novelty": ProviderConfig(model="cheap-extraction")},
        role_panels={
            "peer_review": [ProviderConfig(model="panel-one"), ProviderConfig(model="panel-two")]
        },
    )
    state = Engine(store, config).create("Inspect rich console", "No execution", demo=True)
    store.artifact(state.id, "paper_orchestra_tex", "draft-v1.tex", "Measured manuscript")
    call = store.reserve(state.id, "paper_orchestra", 1, "writer", kind="aggregate")
    store.settle(
        call,
        Usage(cost_usd=0.2, input_tokens=10, output_tokens=20),
        subordinate_calls=[
            SubordinateCall(
                namespace="paper_orchestra",
                id="writer-child",
                provider="xai",
                model="writer-model",
                usage=Usage(cost_usd=0.2, input_tokens=10, output_tokens=20),
            )
        ],
        stage=state.stage,
    )

    store.event(
        state.id,
        "agent_cache",
        state.stage,
        {
            "role": "limitations",
            "model": None,
            "provider": None,
            "provenance_status": "legacy_unknown",
            "configured_model": "configured-not-observed",
            "configured_provider": "configured-provider",
            "configured_route": "default",
            "lookup_request_sha256": "a" * 64,
            "call_id": None,
        },
    )

    async def scenario() -> None:
        app = ResearchApp(store, config, state.id)
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            assert app.selected_run == state.id
            assert store.get_run(state.id).stage == state.stage
            assert not app.controller.busy()
            routing = app.query_one("#routing-detail", TextArea).text
            assert "cheap-extraction" in routing and "panel-two" in routing
            assert "writer-model" in routing and '"subordinate_calls": 1' in routing
            assert '"cost_usd": 0.2' in routing
            assert '"provenance_status": "legacy_unknown"' in routing
            assert '"configured_model": "configured-not-observed"' in routing
            assert '"model": null' in routing and '"lookup_request_sha256"' in routing
            assert "draft-v1.tex" in app.query_one("#artifacts-detail", TextArea).text
            fidelity = app.query_one("#fidelity-detail", TextArea).text
            assert '"scientific_parity": false' in fidelity
            assert "attempt_denominators" in fidelity and "docs/evaluation.md" in fidelity
            assert store.usage(state.id)["calls"] == 1
        app.controller.join()

    asyncio.run(scenario())


def test_direct_cli_app_run_joins_checkpoint_workers_on_terminal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from textual.app import App

    app = ResearchApp(Store(tmp_path))
    joined = []

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("terminal disconnected")

    monkeypatch.setattr(App, "run", fail)
    monkeypatch.setattr(app.controller, "join", lambda: joined.append(True))
    with pytest.raises(RuntimeError, match="terminal disconnected"):
        app.run()
    assert joined == [True]


def test_refresh_callback_after_terminal_shutdown_does_not_query_removed_widgets(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path))
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
        # A queued interval can run while Textual tears down children. The app
        # marks itself stopped before removing them; a late refresh must return.
        assert not app.is_running
        app.refresh_state()
        app.controller.join()

    asyncio.run(scenario())


def test_tui_opens_checkpoint_without_starting_research(tmp_path: Path) -> None:
    async def inspect() -> None:
        store = Store(tmp_path)
        run = Engine(store).create("Saved project", "Inspect only", demo=True)
        app = ResearchApp(store, ResearchConfig(), run.id)
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            assert app.selected_run == run.id
            assert store.get_run(run.id).stage == run.stage
            assert store.usage(run.id)["calls"] == 0
            assert "Saved project" in str(app.query_one("#summary", Static).render())
            assert app.query_one("#intervention", TextArea) is not None
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
            assert "Retain diagnostics" in app.query_one("#overview-text", TextArea).text
            assert "ai_behavior" in app.query_one("#artifacts-detail", TextArea).text
            assert store.usage(run.id)["calls"] == 0

    asyncio.run(inspect())


def test_distinct_runs_have_independent_workers_and_close_pauses_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.tui import ResearchWorkers

    store = Store(tmp_path)
    runs = [
        Engine(store).create(f"Parallel {index}", "Independent checkpoints", demo=True)
        for index in range(2)
    ]
    entered = {run.id: threading.Event() for run in runs}
    release = threading.Event()

    def checkpoint(self: Engine, run_id: str, max_steps: int | None = None) -> RunState:
        with self.store.lease(run_id):
            entered[run_id].set()
            assert release.wait(5)
            state = self.store.get_run(run_id)
            state.status = "paused" if self.store.is_paused(run_id) else "ready"
            self.store.save(state)
            return state

    monkeypatch.setattr(Engine, "run", checkpoint)
    controller = ResearchWorkers(store)
    try:
        for run in runs:
            controller.start(run.id)
        assert all(event.wait(5) for event in entered.values())
        assert all(controller.busy(run.id) for run in runs)
        with pytest.raises(RuntimeError, match="active worker"):
            controller.start(runs[0].id)
        controller.request_close()
        assert all(store.is_paused(run.id) for run in runs)
    finally:
        release.set()
        controller.join()
    assert all(store.get_run(run.id).status == "paused" for run in runs)
    assert not controller.busy()


def test_routing_preview_distinguishes_native_disabled_and_demo_models() -> None:
    from autoresearch.tui import routing_details

    config = ResearchConfig()
    config.paper_orchestra.writer_model_name = "operator-native-writer"
    live = routing_details(config)["resolved_agents"]
    assert live["draft"]["resolved_model"] == "operator-native-writer"
    assert live["draft"]["resolved_provider"] == "native_upstream"
    assert live["laya_triage"]["resolved_model"] == "disabled"
    config.laya.enabled = True
    config.laya.model = "operator-typed-model"
    assert (
        routing_details(config)["resolved_agents"]["laya_triage"]["resolved_model"]
        == "operator-typed-model"
    )
    config.mode = "demo"
    demo = routing_details(config)["resolved_agents"]
    assert demo["draft"]["resolved_model"] == "offline-fixture"
    assert demo["laya_triage"]["resolved_model"] == "disabled"


def test_saved_prompt_inspector_does_not_substitute_changed_local_instructions(
    tmp_path: Path,
) -> None:
    import shutil

    from autoresearch.catalog import ROOT

    specs = tmp_path / "specs"
    shutil.copytree(ROOT, specs)
    prompt = specs / "prompts/limitations.md"
    prompt.write_text(prompt.read_text() + "\nORIGINAL_RECORDED_INSTRUCTION\n")
    config = ResearchConfig(specification_dir=str(specs))
    store = Store(tmp_path / "private")
    state = Engine(store, config).create(
        "Archived prompt", "Inspect the recorded policy", demo=True
    )
    prompt.write_text("CHANGED_LOCAL_INSTRUCTION\n")

    async def scenario() -> None:
        app = ResearchApp(store, config, state.id)
        async with app.run_test(size=(120, 45)) as pilot:
            app.query_one("#system-agent", Select).value = "limitations"
            await pilot.pause()
            original = app.query_one("#text-instructions", TextArea).text
            assert "ORIGINAL_RECORDED_INSTRUCTION" in original
            assert "CHANGED_LOCAL_INSTRUCTION" not in original
            assert app.query_one("#text-instructions", TextArea).read_only
            assert store.usage(state.id)["calls"] == 0
        app.controller.join()

    asyncio.run(scenario())


class FakeTerminalRemote:
    def __init__(self):
        self.saved = {}
        self.calls = []
        self.closed = threading.Event()
        self.auth_status = "authenticating"

    def hosts(self):
        return ["example-cluster"]

    def profiles(self):
        return list(self.saved.values())

    def save_profile(self, profile):
        self.saved[profile["name"]] = profile
        return {"status": "saved"}

    def probe(self, name):
        self.calls.append(("check", name))
        return {"status": "ready"}

    def install(self, name):
        self.calls.append(("install", name))
        return {"status": "installed"}

    def connect(self, name):
        self.calls.append(("connect", name))
        return {"status": "connected", "url": "http://127.0.0.1:9001/#remote-token=private-link"}

    def status(self, name):
        return {"status": "connected"}  # Public status deliberately omits token/URL.

    def disconnect(self, name):
        self.calls.append(("disconnect", name))
        return {"status": "disconnected", "message": "Remote research continues."}

    def authenticate(self, name):
        self.calls.append(("login", name))
        return self.authentication("session-1")

    def authentication(self, session):
        return {"status": self.auth_status, "session_id": session, "output": "Verification code:"}

    def answer_authentication(self, session, answer):
        self.calls.append(("answer", session, answer))
        self.auth_status = "authenticated"
        return self.authentication(session)

    def cancel_authentication(self, session):
        self.calls.append(("cancel", session))
        self.auth_status = "cancelled"
        return self.authentication(session)

    def close(self):
        self.closed.set()


async def remote_form(app, pilot):
    app.query_one("#details", TabbedContent).active = "remote-tab"
    await settle(app, pilot)
    app.query_one("#remote-name", Input).value = "cluster"
    app.query_one("#remote-host", Input).value = "user@cluster.example.org"
    app.query_one("#remote-port", Input).value = "2222"
    await click_visible(app, pilot, "#remote-save")
    await settle(app, pilot)


def test_remote_tab_custom_profile_explicit_install_connect_and_private_link(tmp_path, monkeypatch):
    manager = FakeTerminalRemote()
    opened = []
    monkeypatch.setattr("autoresearch.cli._remote_profile", lambda **values: values)
    monkeypatch.setattr("autoresearch.tui.webbrowser.open", lambda url: opened.append(url) or True)

    async def scenario():
        app = ResearchApp(Store(tmp_path), remote_manager=manager)
        async with app.run_test(size=(110, 40)) as pilot:
            await remote_form(app, pilot)
            assert manager.saved["cluster"]["host"] == "user@cluster.example.org"
            assert manager.saved["cluster"]["port"] == 2222
            assert manager.calls == []
            for action in ("check", "install", "connect"):
                await click_visible(app, pilot, "#remote-" + action)
                await settle(app, pilot)
            assert "private-link" in app.query_one("#remote-url", TextArea).text
            assert "private-link" not in app.query_one("#remote-result", TextArea).text
            assert "private-link" not in str(app.query_one("#notice", Static).render())
            assert opened == []
            await click_visible(app, pilot, "#remote-status")
            await settle(app, pilot)
            assert "private-link" in app.query_one("#remote-url", TextArea).text
            await click_visible(app, pilot, "#remote-open")
            await settle(app, pilot)
            assert len(opened) == 1
            app._remote_profiles["other"] = {**manager.saved["cluster"], "name": "other"}
            app.query_one("#remote-name", Input).value = "other"
            app._remote_submit("status")
            await settle(app, pilot)
            assert not app.query_one("#remote-url", TextArea).text
            app.query_one("#remote-name", Input).value = "cluster"
            app._remote_submit("connect")
            await settle(app, pilot)
            await click_visible(app, pilot, "#remote-disconnect")
            await settle(app, pilot)
            assert not app.query_one("#remote-url", TextArea).text
            assert "Remote research continues" in app.query_one("#remote-result", TextArea).text
            assert app.store.list_runs() == []
        app.controller.join()
        assert manager.closed.wait(2)

    asyncio.run(scenario())


def test_remote_mfa_is_masked_cleared_and_can_be_cancelled(tmp_path, monkeypatch):
    manager = FakeTerminalRemote()
    monkeypatch.setattr("autoresearch.cli._remote_profile", lambda **values: values)

    async def scenario():
        app = ResearchApp(Store(tmp_path), remote_manager=manager)
        async with app.run_test(size=(110, 40)) as pilot:
            await remote_form(app, pilot)
            await click_visible(app, pilot, "#remote-login")
            await settle(app, pilot)
            answer = app.query_one("#remote-auth-answer", Input)
            assert answer.password
            assert "Verification code" in app.query_one("#remote-auth-output", TextArea).text
            answer.value = "private-response"
            app._remote_busy = True  # Enter arriving while a poll is pending must not lose input.
            app._remote_submit("answer")
            assert answer.value == "private-response"
            assert not any(call[0] == "answer" for call in manager.calls)
            app._remote_busy = False
            app._remote_submit("answer")
            assert answer.value == ""
            await settle(app, pilot)
            assert ("answer", "session-1", "private-response") in manager.calls
            assert app._remote_session is None
            assert "private-response" not in app.query_one("#remote-result", TextArea).text
            manager.auth_status = "authenticating"
            app._remote_submit("login")
            await settle(app, pilot)
            answer.value = "unsent-secret"
            app._remote_submit("cancel")
            assert answer.value == ""
            await settle(app, pilot)
            assert ("cancel", "session-1") in manager.calls
            assert app._remote_session is None
        app.controller.join()

    asyncio.run(scenario())


def test_remote_worker_is_responsive_and_failure_is_visible(tmp_path, monkeypatch):
    manager = FakeTerminalRemote()
    entered, release = threading.Event(), threading.Event()

    def check(name):
        entered.set()
        assert release.wait(5)
        raise RuntimeError("SSH authentication failed; use Sign in / MFA and retry.")

    manager.probe = check
    monkeypatch.setattr("autoresearch.cli._remote_profile", lambda **values: values)

    async def scenario():
        app = ResearchApp(Store(tmp_path), remote_manager=manager)
        try:
            async with app.run_test(size=(110, 40)) as pilot:
                await remote_form(app, pilot)
                app._remote_submit("check")
                for _ in range(20):
                    await pilot.pause(0.02)
                    if entered.is_set():
                        break
                assert entered.is_set()
                await pilot.press("ctrl+n")
                assert app.query_one("#details", TabbedContent).active == "new"
                release.set()
                await settle(app, pilot)
                assert "SSH authentication failed" in app.query_one("#remote-result", TextArea).text
        finally:
            release.set()
            app.controller.join()

    asyncio.run(scenario())
