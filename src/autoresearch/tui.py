"""Interactive console over the same durable engine and evidence as the web UI."""

from __future__ import annotations

import json
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from .config import ResearchConfig
from .engine import Engine
from .store import Store


class ResearchApp(App[None]):
    TITLE = "ScientistTwo research console"
    CSS = """
    #controls { height: 3; }
    #controls Button { min-width: 9; margin-right: 1; }
    #status { height: auto; max-height: 5; padding: 0 1; }
    #runs { margin: 0 1; }
    TabbedContent { height: 1fr; }
    TextArea { height: 1fr; }
    #new Button, #intervention Button { margin: 1; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh")]

    def __init__(self, store: Store, config: ResearchConfig | None = None, run_id: str | None = None):
        super().__init__()
        self.store = store
        self.config = config or ResearchConfig()
        self.engine = Engine(store, self.config)
        self.run_id = run_id
        self.busy = False
        self.active_run_id: str | None = None
        self.exit_after_checkpoint = False
        self.run_options: list[tuple[str, str]] = []
        self.last_version = -1

    def compose(self) -> ComposeResult:
        yield Header()
        yield Select[str]([], prompt="Select a saved project", id="runs")
        with Horizontal(id="controls"):
            for name in ("Start", "Step", "Resume", "Pause", "Refresh"):
                yield Button(name, id=name.lower())
        yield Static("Create or select a project. Execution starts only with Start, Step or Resume.", id="status")
        with TabbedContent():
            for ident, title in (("state", "Stages"), ("agents", "Agents / cost"), ("experiments", "Experiments"), ("artifacts", "Artifacts"), ("fidelity", "Fidelity")):
                with TabPane(title, id=f"tab-{ident}"):
                    yield TextArea("", read_only=True, id=f"text-{ident}")
            with TabPane("New project", id="new"):
                yield Input(placeholder="Research title", id="title")
                yield Input(placeholder="Research objective", id="objective")
                yield Static("Uses the configuration supplied with --config; inspect routing before Start.")
                yield Button("Create live project", id="create")
                yield Button("Create offline demo", id="demo")
            with TabPane("Decision / feedback", id="intervention"):
                yield Input(placeholder="Record approval, scientific feedback, or override rationale", id="note")
                yield Input(placeholder="Optional stage identifier", id="stage")
                yield Button("Save intervention", id="intervene")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()
        self.set_interval(2, self.action_refresh)

    def _text(self, name: str, value: Any) -> None:
        self.query_one(f"#text-{name}", TextArea).load_text(json.dumps(value, indent=2, default=str))

    def action_refresh(self) -> None:
        options = [(f"{r['title']} · {r['status']}", str(r["id"])) for r in self.store.list_runs()]
        selection = self.query_one("#runs", Select)
        if options != self.run_options:
            self.run_options = options
            selection.set_options(options)
            if self.run_id:
                selection.value = self.run_id
        if not self.run_id:
            return
        run = self.store.get_run(self.run_id)
        self.query_one("#status", Static).update(f"{run.title} | {run.stage} | {run.status} | {run.error or run.outcome}")
        self._text("state", {"stage": run.stage, "status": run.status, "feedback": run.feedback, "counters": run.counters, "ideas": [i.model_dump() for i in run.ideas], "memory": run.memory})
        config = self.store.get_config(run.id)
        events: list[dict[str, Any]] = []
        while batch := self.store.events(run.id, events[-1]["seq"] if events else 0):
            events.extend(batch)
        self._text("agents", {"usage": self.store.usage(run.id), "routing": {"default": config.provider.model_dump(), "roles": {k: v.model_dump() for k, v in config.role_providers.items()}, "panels": {k: [p.model_dump() for p in v] for k, v in config.role_panels.items()}}, "events": events[-200:]})
        self._text("experiments", [e.model_dump() for e in run.experiments])
        self._text("artifacts", {"root": str(self.store.run_dir(run.id)), "files": self.store.artifacts(run.id), "reviews": run.reviews})
        from .fidelity import load_matrix
        self._text("fidelity", load_matrix())

    def action_quit(self) -> None:
        if self.busy and self.active_run_id:
            self.engine.pause(self.active_run_id)
            self.exit_after_checkpoint = True
            self.notify("Pause requested. Closing after the active checkpoint.")
        else:
            self.exit()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self.run_id = str(event.value)
            self.action_refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.id
        try:
            if action in {"create", "demo"}:
                run = self.engine.create(self.query_one("#title", Input).value or "Research project", self.query_one("#objective", Input).value or "Investigate the registered research protocol", demo=action == "demo")
                self.run_id = run.id
            elif action == "refresh":
                pass
            elif not self.run_id:
                self.notify("Select a project first", severity="warning")
            elif action == "pause":
                self.engine.pause(self.run_id)
            elif action == "intervene":
                self.engine.intervene(self.run_id, note=self.query_one("#note", Input).value, stage=self.query_one("#stage", Input).value or None)
            elif action in {"start", "step", "resume"}:
                if self.busy:
                    self.notify("A worker is already active", severity="warning")
                else:
                    self.execute(self.run_id, action)
            self.action_refresh()
        except (ValueError, RuntimeError, OSError) as exc:
            self.notify(str(exc), severity="error")

    @work(thread=True, exclusive=True)
    def execute(self, run_id: str, action: str) -> None:
        self.busy = True
        self.active_run_id = run_id
        try:
            if action == "resume":
                self.engine.resume(run_id)
            self.engine.run(run_id, max_steps=1 if action == "step" else None)
        except (ValueError, RuntimeError, OSError) as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")
        finally:
            self.busy = False
            self.active_run_id = None
            self.call_from_thread(self.exit if self.exit_after_checkpoint else self.action_refresh)
