"""A local terminal console over the persisted research engine; no HTTP server."""

from __future__ import annotations

import json
import queue
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
    Tree,
)

from .behavior import describe, inspect_run
from .config import ResearchConfig, load_config
from .contracts import RunState, Stage
from .engine import Engine
from .privacy import redact
from .store import Store
from .system_view import prompt_text, system_text


def display(value: Any) -> str:
    """Treat research text as plain data, redact secrets, remove terminal controls."""
    cleaned = redact(value)
    text = (
        cleaned if isinstance(cleaned, str) else json.dumps(cleaned, indent=2, ensure_ascii=False)
    )
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", text)


def readiness_text(report: Any) -> str:
    heading = "READY FOR LIVE RESEARCH" if report["ready"] else "SETUP NEEDS ATTENTION"
    checks = "\n\n".join(
        f"[{check['status'].upper()}] {check['name']}\n{check['message']}"
        for check in report["checks"]
    )
    return f"{heading}\n\n{checks}"


def routing_details(
    config: ResearchConfig, recorded: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Project saved facts and the authoritative behavior resolver, without re-routing in UI."""
    info = describe(config) if recorded is None else recorded
    return {
        "configuration": config.model_dump(
            mode="json",
            include={
                "mode",
                "provider",
                "cheap_provider",
                "frontier_provider",
                "role_providers",
                "role_panels",
                "heldout_provider",
                "role_commands",
                "role_command_max_cost_usd",
                "paper_orchestra",
                "laya",
            },
        ),
        "resolution_source": "current_configuration" if recorded is None else "recorded_run_bundle",
        "resolved_agents": {
            role: {
                key: agent[key]
                for key in (
                    "resolved_model",
                    "resolved_provider",
                    "configured_model",
                    "routing_reason",
                    "prompt_scope",
                    "upstream_models",
                )
                if key in agent
            }
            for role, agent in info.get("agents", {}).items()
        },
        "resolution_available": bool(info.get("agents")),
        "configuration_note": "Change routing in configuration before creating a new run. Saved-run behavior stays fixed; per-call receipts record actual escalation, panels and usage. Budget limits can be changed in Controls.",
    }


def overview_text(state: RunState) -> str:
    lines = [
        "OBJECTIVE",
        state.objective,
        "",
        f"Stage: {state.stage.value} · Round: {state.round}",
        f"Current idea: {state.current_idea or 'None yet'}",
        f"Selected candidate: {state.selected_idea or 'None yet'}",
    ]
    if state.baseline:
        lines += [
            "",
            "REPRODUCED BASELINE",
            *[f"{name}: {value:g}" for name, value in state.baseline.items()],
        ]
    if state.limitations:
        lines += [
            "",
            "VERIFIED LIMITATIONS",
            *[f"{index}. {value}" for index, value in enumerate(state.limitations, 1)],
        ]
    for heading, value in (
        ("LATEST FEEDBACK", state.feedback),
        ("REQUIRED ATTENTION", state.error),
        ("OUTCOME", state.outcome),
    ):
        if value:
            lines += ["", heading, value]
    if state.pending_job_id:
        lines += ["", f"Scheduler job: {state.pending_job_id}"]
    return "\n".join(lines)


@dataclass
class Update:
    operation: str
    run_id: str | None = None
    value: Any = None
    error: str = ""


class ResearchWorkers:
    """Non-daemon workers finish their checkpoint before application shutdown.

    Only the UI thread touches widgets. Workers exchange results via a queue and
    the engine's durable store/leases. Closing never abruptly kills experiments.
    """

    def __init__(self, store: Store) -> None:
        self.store = store
        self.updates: queue.SimpleQueue[Update] = queue.SimpleQueue()
        self._threads: dict[str, threading.Thread] = {}
        self._run_ids: dict[str, str] = {}
        self._pause_requests: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self.closing = threading.Event()

    def busy(self, run_id: str | None = None) -> bool:
        with self._lock:
            return any(
                thread.is_alive() and (run_id is None or self._run_ids.get(key) == run_id)
                for key, thread in self._threads.items()
            )

    def submit(self, operation: str, task: Callable[[], Any], run_id: str | None = None) -> None:
        with self._lock:
            if self.closing.is_set():
                raise RuntimeError("The console is finishing active checkpoints before exit")
            key = run_id or operation
            previous = self._threads.get(key)
            if previous and previous.is_alive():
                raise RuntimeError("This operation already has an active worker")

            def execute() -> None:
                try:
                    value = task()
                    result_id = value.id if isinstance(value, RunState) else run_id
                    if result_id and self.closing.is_set():
                        Engine(self.store).pause(result_id)
                    self.updates.put(Update(operation, result_id, value))
                except Exception as error:
                    self.updates.put(Update(operation, run_id, error=display(str(error))))

            thread = threading.Thread(target=execute, name=f"research-tui-{key}", daemon=False)
            self._threads[key] = thread
            if run_id:
                self._run_ids[key] = run_id
            thread.start()

    def start(self, run_id: str, *, steps: int | None = None) -> None:
        pause_requested = threading.Event()

        def execute() -> RunState:
            config = self.store.get_config(run_id)
            if config.mode == "live":
                from .setup import validate_live_config

                # Resuming uses the private source snapshot; the original source
                # directory may legitimately have moved after run creation.
                config.project.source_dir = str(self.store.run_dir(run_id) / "source")
                validate_live_config(config)
            if self.closing.is_set():
                return self.store.get_run(run_id)
            engine = Engine(self.store)
            engine.resume(run_id)
            # Close may have raced resume; reapply pause before entering a step.
            if self.closing.is_set() or pause_requested.is_set():
                engine.pause(run_id)
            return engine.run(run_id, max_steps=steps)

        with self._lock:
            if self.busy(run_id):
                raise RuntimeError("This run already has an active worker")
            self._pause_requests[run_id] = pause_requested
            self.submit("step" if steps else "run", execute, run_id)

    def pause(self, run_id: str) -> None:
        with self._lock:
            requested = self._pause_requests.get(run_id)
            if requested is not None:
                requested.set()
        Engine(self.store).pause(run_id)

    def request_close(self) -> None:
        self.closing.set()
        with self._lock:
            run_ids = set(self._run_ids.values())
        for run_id in run_ids:
            if self.busy(run_id):
                self.pause(run_id)

    def join(self) -> None:
        self.request_close()
        with self._lock:
            threads = list(self._threads.values())
        for thread in threads:
            thread.join()


class ResearchApp(App[None]):
    TITLE = "ScientistTwo · Research console"
    SUB_TITLE = "Private local state · checkpoints persist across sessions"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+n", "new", "New"),
        Binding("ctrl+r", "run", "Run / resume"),
        Binding("ctrl+s", "step", "Step"),
        Binding("ctrl+p", "pause", "Pause", priority=True),
        Binding("ctrl+q", "quit", "Save & exit", priority=True),
        Binding("ctrl+c", "quit", "Save & exit", show=False, priority=True),
    ]
    CSS = """
    Screen { background: $background; }
    #body { height: 1fr; }
    #sidebar { width: 29; min-width: 22; border-right: solid $primary-muted; padding: 0 1; }
    #sidebar-title { height: 2; text-style: bold; padding-top: 1; }
    #runs { height: 1fr; }
    #new-run { width: 100%; margin-top: 1; }
    #main { width: 1fr; padding: 0 1; }
    #summary { height: 5; padding: 1 0 0 0; }
    #actions { height: 3; }
    #actions Button { min-width: 8; width: 1fr; margin-right: 1; }
    #details { height: 1fr; }
    TabPane { padding: 1 0 0 0; }
    #overview-text { height: 45%; min-height: 4; }
    #ideas { height: 1fr; }
    #experiments, #events { height: 40%; min-height: 4; }
    #experiment-detail, #event-detail, #manuscript { height: 1fr; }
    #text-system { height: 45%; min-height: 5; }
    #text-instructions { height: 1fr; }
    TextArea { border: solid $primary-muted; }
    Label { margin-top: 1; height: auto; }
    .form { padding: 0 1; }
    .form Input, .form Select { width: 100%; }
    .form TextArea { height: 5; }
    .form Horizontal { height: 3; margin-top: 1; }
    .form Button { width: 1fr; min-width: 10; margin-right: 1; }
    #setup-result { height: 10; margin-top: 1; }
    #notice { height: 2; padding: 0 1; background: $panel; color: $text-muted; }
    .hint { color: $text-muted; height: auto; margin: 1 0; }
    """

    def __init__(
        self,
        store: Store,
        config: ResearchConfig | None = None,
        run_id: str | None = None,
        *,
        config_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.config = config.model_copy(deep=True) if config else ResearchConfig()
        self._configuration_supplied = config is not None
        self.config_path = config_path
        self.selected_run = run_id
        if run_id:
            store.get_run(run_id)
        self.controller = ResearchWorkers(store)
        self._run_signature: str = ""
        self._state_signature: tuple[str, int] | None = None
        self._events: dict[str, dict[str, Any]] = {}
        self._event_cursor = 0
        self._selected_experiment: str | None = None
        self._loaded_run: str | None = None
        self._artifact_signature = ""
        self._routing_signature = ""
        self.system_identity: tuple[str, str] | None = None
        self.system_info: dict[str, Any] = {}

    def run(self, *args: Any, **kwargs: Any) -> None:
        try:
            super().run(*args, **kwargs)
        finally:
            self.controller.join()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("RESEARCH HISTORY", id="sidebar-title", markup=False)
                yield DataTable(id="runs", cursor_type="row", zebra_stripes=True)
                yield Button("New research", id="new-run", variant="primary")
            with Vertical(id="main"):
                yield Static(
                    "Choose a run or create a new research project.", id="summary", markup=False
                )
                with Horizontal(id="actions"):
                    yield Button("Run / resume", id="run", variant="success")
                    yield Button("Step", id="step")
                    yield Button("Pause", id="pause", variant="warning")
                    yield Button("Refresh", id="refresh")
                with TabbedContent(id="details", initial="new"):
                    with TabPane("Overview", id="overview"):
                        yield TextArea(read_only=True, show_cursor=False, id="overview-text")
                        yield Tree("Research tree", id="ideas")
                    with TabPane("Experiments", id="experiments-tab"):
                        yield DataTable(id="experiments", cursor_type="row", zebra_stripes=True)
                        yield TextArea(read_only=True, show_cursor=False, id="experiment-detail")
                    with TabPane("Activity", id="activity"):
                        yield DataTable(id="events", cursor_type="row", zebra_stripes=True)
                        yield TextArea(read_only=True, show_cursor=False, id="event-detail")
                    with TabPane("Manuscript", id="manuscript-tab"):
                        yield TextArea(read_only=True, show_cursor=False, id="manuscript")
                    with TabPane("Agents / costs", id="agents-tab"):
                        yield TextArea(read_only=True, show_cursor=False, id="routing-detail")
                    with TabPane("AI system", id="system-tab"):
                        yield Select[str](
                            [], prompt="Inspect recorded agent instructions", id="system-agent"
                        )
                        yield TextArea(
                            "Select a saved run to inspect its recorded AI system.",
                            read_only=True,
                            show_cursor=False,
                            id="text-system",
                        )
                        yield TextArea(
                            "Original instructions become available from a saved run's behavior bundle.",
                            read_only=True,
                            show_cursor=False,
                            id="text-instructions",
                        )
                    with TabPane("Artifacts", id="artifacts-tab"):
                        yield TextArea(read_only=True, show_cursor=False, id="artifacts-detail")
                    with TabPane("Fidelity / evaluation", id="fidelity-tab"):
                        yield TextArea(read_only=True, show_cursor=False, id="fidelity-detail")
                    with TabPane("Controls", id="controls"):
                        with VerticalScroll(classes="form"):
                            yield Static(
                                "Pause and wait for the active checkpoint before editing a run.",
                                classes="hint",
                                markup=False,
                            )
                            yield Label("Researcher feedback")
                            yield TextArea(
                                id="intervention",
                                placeholder="Record evidence, corrections, or directions",
                            )
                            yield Select(
                                [
                                    ("Keep current stage", ""),
                                    *[
                                        (stage.value, stage.value)
                                        for stage in Stage
                                        if stage != Stage.COMPLETE
                                    ],
                                ],
                                value="",
                                allow_blank=False,
                                id="stage",
                            )
                            with Horizontal():
                                yield Button("Save intervention", id="intervene")
                                yield Button("Cancel Slurm job", id="cancel-job", variant="error")
                            yield Label("Total API budget (USD)")
                            yield Input(id="budget-usd", type="number")
                            yield Label("Maximum model calls")
                            yield Input(id="budget-calls", type="integer")
                            yield Label("Maximum experiments")
                            yield Input(id="budget-experiments", type="integer")
                            yield Label("Wall-time limit (seconds since run creation)")
                            yield Input(id="budget-wall", type="integer")
                            with Horizontal():
                                yield Button("Update budget", id="save-budget", variant="primary")
                    with TabPane("New run", id="new"):
                        with VerticalScroll(classes="form"):
                            yield Static(
                                "Live research uses your configured models and budget. Demo explicitly uses offline fixtures.",
                                classes="hint",
                                markup=False,
                            )
                            yield Label("Configuration file (required for live research)")
                            yield Input(
                                str(self.config_path or ""),
                                placeholder="/path/to/research.json",
                                id="config-path",
                            )
                            yield Static(
                                "Role providers, heterogeneous panels and writer models come from this JSON configuration. Check setup to preview routing before creating a run. Saved-run routing remains fixed.",
                                classes="hint",
                                markup=False,
                            )
                            yield Label("Research title")
                            yield Input(placeholder="Your research project", id="new-title")
                            yield Label("Objective")
                            yield TextArea(
                                id="new-objective",
                                placeholder="What should the system investigate?",
                            )
                            with Horizontal():
                                yield Button("Check setup", id="check-setup")
                                yield Button("Create live", id="create-live", variant="success")
                                yield Button("Create demo", id="create-demo")
                            yield TextArea(
                                "Load a config and check setup before live research. Creating a run does not start paid work.",
                                read_only=True,
                                show_cursor=False,
                                id="setup-result",
                            )
        yield Static(
            "Ready. Ctrl+N: new · Ctrl+R: run · Ctrl+S: one step · Ctrl+P: checkpoint pause",
            id="notice",
            markup=False,
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#runs", DataTable).add_columns("Run", "Stage / status")
        self.query_one("#experiments", DataTable).add_columns("Experiment", "Status", "Metrics")
        self.query_one("#events", DataTable).add_columns("#", "Time", "Stage", "Event")
        from .fidelity import load_matrix

        self._text("#fidelity-detail", load_matrix())
        try:
            self._text("#routing-detail", routing_details(self.config))
        except (ValueError, RuntimeError, OSError) as exc:
            self._text("#routing-detail", {"configuration_error": str(exc)})
        self._text(
            "#artifacts-detail",
            "Select a saved run to inspect versioned artifact paths, hashes and reviews.",
        )
        self.refresh_state()
        if self.selected_run and self.config_path is None:
            self.query_one("#details", TabbedContent).active = "overview"
        self.set_interval(0.5, self.refresh_state)

    def notice(self, message: str) -> None:
        self.query_one("#notice", Static).update(display(message))

    def _text(self, widget: str, value: Any) -> None:
        area = self.query_one(widget, TextArea)
        content = display(value)
        if area.text != content:
            area.load_text(content)

    def refresh_state(self) -> None:
        # Textual marks the app stopped before unmounting children; an already
        # queued interval callback must not query the disappearing widget tree.
        if not self.is_running:
            return
        while not self.controller.updates.empty():
            update = self.controller.updates.get()
            if update.error:
                self.notice(update.error)
                if update.operation in {"create", "preflight"}:
                    self._text("#setup-result", update.error)
            elif update.operation == "preflight":
                self._text("#setup-result", readiness_text(update.value))
                if "routing" in update.value:
                    self._text("#routing-detail", update.value["routing"])
                self.notice(
                    "Setup check finished. Review every error and warning before live research."
                )
            else:
                if update.operation == "create" and update.run_id:
                    self.select_run(update.run_id)
                self.notice(f"{update.operation.capitalize()} finished; checkpoint saved.")
                if update.operation == "budget":
                    self._load_budget()
        rows = self.store.list_runs()
        signature = json.dumps(rows, sort_keys=True)
        if signature != self._run_signature:
            self._run_signature = signature
            table = self.query_one("#runs", DataTable)
            cursor_run = self.selected_run
            if table.has_focus and table.row_count:
                cursor_run = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            table.clear()
            for row in rows:
                table.add_row(
                    Text(display(row["title"])),
                    Text(f"{row['stage']} / {row['status']}"),
                    key=row["id"],
                )
            if self.selected_run is None and rows:
                self.selected_run = rows[0]["id"]
            for index, row in enumerate(rows):
                if row["id"] == cursor_run:
                    table.move_cursor(row=index)
        if self.selected_run:
            self._refresh_selected()
        busy = self.controller.busy(self.selected_run) if self.selected_run else False
        for button in ("run", "step", "intervene", "save-budget", "cancel-job"):
            self.query_one(f"#{button}", Button).disabled = (
                not self.selected_run or busy or self.controller.closing.is_set()
            )
        if self.selected_run:
            state = self.store.get_run(self.selected_run)
            if state.status in {"completed", "failed", "stopped"} or state.stage == Stage.COMPLETE:
                self.query_one("#run", Button).disabled = True
                self.query_one("#step", Button).disabled = True
        self.query_one("#pause", Button).disabled = (
            not self.selected_run or self.controller.closing.is_set()
        )
        if self.controller.closing.is_set() and not self.controller.busy():
            self.exit()

    def _refresh_selected(self) -> None:
        assert self.selected_run is not None
        state = self.store.get_run(self.selected_run)
        usage = self.store.usage(state.id)
        config = self.store.get_config(state.id)
        mode = config.mode.upper()
        status = "pause requested" if self.store.is_paused(state.id) else state.status
        if self.controller.busy(state.id):
            status += " · worker active"
        title_width = max(8, self.size.width - 56)
        title = (
            state.title if len(state.title) <= title_width else state.title[: title_width - 1] + "…"
        )
        self.query_one("#summary", Static).update(
            display(
                f"{mode} {state.id} · {title}\n{state.stage.value} / {status}\n"
                f"API ${usage['cost_usd']:.4f} / ${usage['budget_usd']:.2f} · held ${usage['reserved_usd']:.4f}\n"
                f"Model calls {usage.get('model_calls_attempted', usage['calls'])} · Experiments {len(state.experiments)}"
            )
        )
        if self._loaded_run != state.id:
            self._loaded_run = state.id
            self._state_signature = None
            self._artifact_signature = ""
            self._routing_signature = ""
            self._events.clear()
            self._event_cursor = 0
            self._selected_experiment = None
            self.query_one("#events", DataTable).clear()
            self.query_one("#experiments", DataTable).clear()
            self._text(
                "#event-detail",
                "Select an activity row to inspect its prompt, result, decision, or usage. Trace visibility follows the run's privacy setting.",
            )
            self._text(
                "#experiment-detail",
                "Select an experiment to inspect its actual metrics, stdout, stderr, and provenance.",
            )
            self._load_budget()
        if self._state_signature != (state.id, state.version):
            self._state_signature = (state.id, state.version)
            self._text("#overview-text", overview_text(state))
            from .fidelity import load_matrix
            from .integrity import attempt_summary

            matrix = load_matrix()
            self._text(
                "#fidelity-detail",
                {
                    "capability_notice": "Offline demos test plumbing. Architecture and review scores do not establish scientific parity.",
                    "run_mode": config.mode,
                    "run_status": state.status,
                    "run_outcome": state.outcome or "unfinished",
                    "attempt_denominators": attempt_summary(state),
                    "evaluation_guide": "docs/evaluation.md; use autoresearch evaluate report SUITE_DIRECTORY for paired public-task measurements",
                    "fidelity_matrix": matrix,
                },
            )
            tree = self.query_one("#ideas", Tree)
            tree.clear()
            tree.root.set_label(Text(f"Research tree · {len(state.ideas)} ideas"))
            for idea in state.ideas:
                node = tree.root.add(Text(display(f"{idea.id} · {idea.title} [{idea.status}]")))
                node.add_leaf(
                    Text(
                        display(
                            f"Round {idea.round} · parents: {', '.join(idea.parents) or 'seed'}"
                        )
                    )
                )
                node.add_leaf(Text(display(idea.hypothesis)))
                node.add_leaf(Text(display(idea.metrics)))
            tree.root.expand()
            self._text(
                "#manuscript",
                state.manuscript
                or "No manuscript yet. Drafts and revisions appear here after measured experiments.",
            )
            table = self.query_one("#experiments", DataTable)
            table.clear()
            for experiment in state.experiments:
                table.add_row(
                    experiment.id,
                    experiment.status,
                    Text(display(experiment.metrics)),
                    key=experiment.id,
                )
            if state.pending_experiment:
                table.add_row(
                    state.pending_experiment.id,
                    "scheduler pending" if state.pending_job_id else "executing",
                    "Awaiting measured result",
                    key=state.pending_experiment.id,
                )
            if state.pending_experiment and self._selected_experiment is None:
                self._selected_experiment = state.pending_experiment.id
            elif state.experiments and self._selected_experiment is None:
                self._selected_experiment = state.experiments[-1].id
            self._show_experiment(state)
        if (
            state.pending_experiment
            and self.query_one("#details", TabbedContent).active == "experiments-tab"
        ):
            self._show_experiment(state)
        events = self.store.events(state.id, after=self._event_cursor)
        table = self.query_one("#events", DataTable)
        for event in events:
            key = str(event["seq"])
            self._events[key] = event
            table.add_row(key, event["timestamp"][11:19], event["stage"], event["kind"], key=key)
            self._event_cursor = event["seq"]
        self._refresh_system(state)
        routing = {
            "usage": usage,
            "routing": routing_details(config, self.system_info),
            "recent_model_calls": [
                {
                    "event_seq": event["seq"],
                    "timestamp": event["timestamp"],
                    "kind": event["kind"],
                    "stage": event["stage"],
                    "details": {
                        key: value
                        for key, value in event["payload"].items()
                        if key
                        in {
                            "id",
                            "role",
                            "agent",
                            "model",
                            "provider",
                            "usage",
                            "status",
                            "estimated",
                            "input_tokens",
                            "output_tokens",
                            "cost_usd",
                            "latency_seconds",
                            "error_type",
                            "request_sha256",
                            "lookup_request_sha256",
                            "provenance_status",
                            "call_id",
                            "configured_model",
                            "configured_provider",
                            "configured_route",
                            "prompt_sha256",
                            "agent_version",
                            "catalog_sha256",
                            "bundle_sha256",
                            "route",
                            "schema_version",
                        }
                    },
                }
                for event in list(self._events.values())[-500:]
                if event["kind"]
                in {
                    "agent_completed",
                    "agent_failed",
                    "agent_cache",
                    "model_escalation",
                    "subordinate_model_call",
                    "paper_orchestra_api_call",
                }
            ][-100:],
        }
        signature = json.dumps(routing, sort_keys=True)
        if signature != self._routing_signature:
            self._routing_signature = signature
            self._text("#routing-detail", routing)
        artifacts = {
            "private_run_directory": str(self.store.run_dir(state.id)),
            "artifacts": self.store.artifacts(state.id),
            "reviews": state.reviews,
        }
        signature = json.dumps(artifacts, sort_keys=True)
        if signature != self._artifact_signature:
            self._artifact_signature = signature
            self._text("#artifacts-detail", artifacts)

    def _refresh_system(self, state: RunState) -> None:
        identity = (state.id, state.behavior.bundle_sha256 if state.behavior else "legacy")
        if identity == self.system_identity:
            return
        try:
            self.system_info = inspect_run(self.store, state)
            self._text("#text-system", system_text(self.system_info))
            self.query_one("#system-agent", Select).set_options(
                [(role, role) for role in self.system_info.get("agents", {})]
            )
            self._text(
                "#text-instructions", "Select an agent to inspect its recorded instructions."
            )
            self.system_identity = identity
        except (ValueError, RuntimeError, OSError) as exc:
            self.system_info = {}
            self.system_identity = None
            self.query_one("#system-agent", Select).set_options([])
            self._text(
                "#text-system",
                f"Recorded AI behavior is unavailable or untrusted: {exc}. The run journal remains inspectable.",
            )
            self._text(
                "#text-instructions",
                "Original instructions unavailable; no current-definition fallback is used.",
            )

    @on(Select.Changed, "#system-agent")
    def agent_selected(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self._text("#text-instructions", prompt_text(self.system_info, str(event.value)))

    def _show_experiment(self, state: RunState) -> None:
        pending = state.pending_experiment
        if pending and self._selected_experiment == pending.id:
            detail: dict[str, Any] = {
                "id": pending.id,
                "status": "scheduler pending" if state.pending_job_id else "executing",
                "job_id": state.pending_job_id,
                "kind": pending.kind,
                "argv": pending.argv,
                "seed": pending.seed,
                "note": "Metrics and complete process logs are recorded when this experiment finishes.",
            }
            if state.pending_job_id:
                from .execution import Executor

                root = Path(pending.workspace)
                if root.resolve().is_relative_to(self.store.run_dir(state.id) / "experiments"):
                    executor = Executor(self.store.get_config(state.id).execution)
                    detail["stdout"] = executor._log(root, ".autoresearch-stdout.log")
                    detail["stderr"] = executor._log(root, ".autoresearch-stderr.log")
            self._text("#experiment-detail", detail)
            return
        selected = next(
            (item for item in state.experiments if item.id == self._selected_experiment), None
        )
        if selected:
            self._text("#experiment-detail", selected.model_dump(mode="json"))

    def _load_budget(self) -> None:
        if not self.selected_run:
            return
        budget = self.store.get_config(self.selected_run).budget
        for name, value in (
            ("usd", budget.usd),
            ("calls", budget.max_calls),
            ("experiments", budget.max_experiments),
            ("wall", budget.wall_seconds),
        ):
            self.query_one(f"#budget-{name}", Input).value = str(value)

    def select_run(self, run_id: str) -> None:
        self.selected_run = run_id
        self.query_one("#details", TabbedContent).active = "overview"
        self._refresh_selected()

    @on(DataTable.RowSelected)
    def row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value)
        if event.data_table.id == "runs":
            self.select_run(key)
        elif event.data_table.id == "events":
            self._text("#event-detail", self._events[key])
        elif event.data_table.id == "experiments" and self.selected_run:
            self._selected_experiment = key
            self._show_experiment(self.store.get_run(self.selected_run))

    def action_new(self) -> None:
        self.query_one("#details", TabbedContent).active = "new"
        self.query_one("#new-title", Input).focus()

    def action_run(self) -> None:
        self._start(None)

    def action_step(self) -> None:
        self._start(1)

    def _start(self, steps: int | None) -> None:
        if not self.selected_run:
            self.notice("Create or select a run first.")
            return
        try:
            state = self.store.get_run(self.selected_run)
            if state.status in {"completed", "failed", "stopped"} or state.stage == Stage.COMPLETE:
                self.notice("This research run is finished.")
                return
            self.controller.start(self.selected_run, steps=steps)
            self.notice(
                "Executing one checkpoint…"
                if steps
                else "Research running. Pause takes effect after the active checkpoint."
            )
            self.refresh_state()
        except (ValueError, RuntimeError, KeyError) as error:
            self.notice(str(error))

    def action_pause(self) -> None:
        if self.selected_run:
            self.controller.pause(self.selected_run)
            self.notice("Pause requested. The active checkpoint will finish safely.")
            self.refresh_state()

    async def action_quit(self) -> None:
        self.controller.request_close()
        if self.controller.busy():
            self.notice(
                "Finishing active checkpoints before exit. Your work remains saved; the console will close automatically."
            )
        else:
            self.exit()

    def on_unmount(self) -> None:
        self.controller.request_close()

    def _configuration(self, path: str) -> ResearchConfig:
        if not path.strip() and self._configuration_supplied:
            config = self.config.model_copy(deep=True)
            config.mode = "live"
            return config
        if not path.strip():
            raise ValueError(
                "Choose a configuration file for live research. Generate one with autoresearch init, then configure your project."
            )
        config = load_config(Path(path).expanduser())
        config.mode = "live"
        return config

    def _create(self, demo: bool) -> None:
        title = self.query_one("#new-title", Input).value.strip()
        objective = self.query_one("#new-objective", TextArea).text.strip()
        path = self.query_one("#config-path", Input).value

        def create() -> RunState:
            if demo:
                config = ResearchConfig(mode="demo")
            else:
                from .setup import preflight

                config = self._configuration(path)
                report = preflight(config, probe_runtime=True)
                if not report["ready"]:
                    raise ValueError(readiness_text(report))
            return Engine(self.store, config).create(
                title or ("Offline research demonstration" if demo else ""),
                objective or ("Evaluate the deterministic synthetic benchmark." if demo else ""),
                demo=demo,
            )

        self.controller.submit("create", create)
        self.notice("Creating private run and source snapshot…")

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        try:
            if button == "new-run":
                self.action_new()
            elif button == "run":
                self.action_run()
            elif button == "step":
                self.action_step()
            elif button == "pause":
                self.action_pause()
            elif button == "refresh":
                self.refresh_state()
            elif button in {"create-live", "create-demo"}:
                self._create(button == "create-demo")
            elif button == "check-setup":
                path = self.query_one("#config-path", Input).value

                def check() -> dict[str, Any]:
                    from .setup import preflight

                    config = self._configuration(path)
                    return {
                        **preflight(config, probe_runtime=True),
                        "routing": routing_details(config),
                    }

                self.controller.submit("preflight", check)
                self.notice("Checking configuration, credentials, and execution tools…")
            elif button == "intervene" and self.selected_run:
                run_id = self.selected_run
                note = self.query_one("#intervention", TextArea).text
                stage = self.query_one("#stage", Select).value
                target_stage = stage if isinstance(stage, str) and stage else None
                self.controller.submit(
                    "intervention",
                    lambda: Engine(self.store).intervene(run_id, note, target_stage),
                    run_id,
                )
            elif button == "save-budget" and self.selected_run:
                run_id = self.selected_run
                usd = float(self.query_one("#budget-usd", Input).value)
                calls = int(self.query_one("#budget-calls", Input).value)
                experiments = int(self.query_one("#budget-experiments", Input).value)
                wall = int(self.query_one("#budget-wall", Input).value)
                self.controller.submit(
                    "budget",
                    lambda: self.store.update_budget(
                        run_id,
                        usd=usd,
                        max_calls=calls,
                        max_experiments=experiments,
                        wall_seconds=wall,
                    ),
                    run_id,
                )
            elif button == "cancel-job" and self.selected_run:
                run_id = self.selected_run
                Engine(self.store).pause(run_id)
                self.controller.submit(
                    "cancellation", lambda: Engine(self.store).cancel_experiment(run_id), run_id
                )
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            self.notice(str(error))


def run_tui(store: Store, *, config_path: Path | None = None, run_id: str | None = None) -> None:
    app = ResearchApp(store, config_path=config_path, run_id=run_id)
    try:
        app.run()
    finally:
        # Covers terminal disconnects and unexpected UI exceptions, in addition
        # to the normal responsive Ctrl+Q checkpoint shutdown.
        app.controller.join()
