"""Small, scriptable CLI for the same engine used by the research console."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import load_config, save_example
from .contracts import RunState, Stage
from .engine import Engine
from .store import Store


def _print(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _print_run(state: RunState) -> int:
    _print(state)
    return 2 if state.status in {"blocked", "failed", "stopped", "budget_exhausted"} else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoresearch", description="ScientistTwo research workflow and local console"
    )
    parser.add_argument(
        "--state-dir", type=Path, help="Private runtime root (or AUTORESEARCH_HOME)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Write an example configuration")
    init.add_argument("path", type=Path, nargs="?", default=Path("autoresearch.example.json"))
    init.add_argument("--demo", action="store_true", help="Configure offline demonstration mode")
    new = commands.add_parser("new", help="Create a research run")
    new.add_argument("--title", required=True)
    new.add_argument("--objective", required=True)
    new.add_argument("--config", type=Path)
    new.add_argument("--demo", action="store_true")
    run = commands.add_parser("run", help="Execute until completion or a checkpoint limit")
    run.add_argument("id")
    run.add_argument("--steps", type=int)
    demo = commands.add_parser("demo", help="Run the complete offline demonstration")
    demo.add_argument("--title", default="Reproducible research demonstration")
    demo.add_argument(
        "--objective", default="Evaluate a deterministic synthetic learning benchmark."
    )
    demo.add_argument("--steps", type=int)
    status = commands.add_parser("status", help="Inspect a run, or list every run")
    status.add_argument("id", nargs="?")
    web = commands.add_parser("serve", help="Open the local web console")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--config", type=Path)
    tui = commands.add_parser("tui", help="Open the interactive terminal research console")
    tui.add_argument("--config", type=Path, help="Prefill the live research configuration path")
    tui.add_argument("--run", dest="run_id", help="Select an existing run without starting it")
    check = commands.add_parser("check", help="Check live configuration and execution readiness")
    check.add_argument("--config", type=Path, required=True)
    for name in ("pause", "resume"):
        command = commands.add_parser(name, help=f"{name.capitalize()} a checkpointed run")
        command.add_argument("id")
    cancel = commands.add_parser(
        "cancel-experiment", help="Cancel a pending Slurm experiment after pausing the run"
    )
    cancel.add_argument("id")
    intervene = commands.add_parser(
        "intervene", help="Record human feedback and optionally change stage"
    )
    intervene.add_argument("id")
    intervene.add_argument("--note", required=True)
    intervene.add_argument("--stage", choices=[stage.value for stage in Stage])
    budget = commands.add_parser("budget", help="Explicitly update a paused run's budget limits")
    budget.add_argument("id")
    budget.add_argument("--usd", type=float)
    budget.add_argument("--calls", type=int)
    budget.add_argument("--experiments", type=int)
    budget.add_argument("--wall-seconds", type=int)
    export = commands.add_parser(
        "export", help="Export a shareable summary, or opt into private data"
    )
    export.add_argument("id")
    export.add_argument("target", type=Path)
    export.add_argument(
        "--include-private",
        action="store_true",
        help="Include potentially sensitive research artifacts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if getattr(args, "steps", None) is not None and args.steps < 1:
        parser.error("--steps must be positive")
    try:
        if args.command == "init":
            if args.path.exists():
                raise ValueError(f"Refusing to overwrite existing configuration: {args.path}")
            save_example(args.path, demo=args.demo)
            print(f"Configuration written to {args.path}")
            return 0
        if args.command == "check":
            from .setup import preflight

            report = preflight(load_config(args.config), probe_runtime=True)
            _print(report)
            return 0 if report["ready"] else 2
        store = Store(args.state_dir)
        engine = Engine(store)
        if args.command == "new":
            engine = Engine(store, load_config(args.config))
            _print(engine.create(args.title, args.objective, demo=args.demo))
        elif args.command == "run":
            return _print_run(engine.run(args.id, max_steps=args.steps))
        elif args.command == "demo":
            state = engine.create(args.title, args.objective, demo=True)
            print(f"Created demonstration run {state.id}", file=sys.stderr)
            return _print_run(engine.run(state.id, max_steps=args.steps))
        elif args.command == "status":
            if args.id:
                _print(
                    {
                        "run": store.get_run(args.id).model_dump(mode="json"),
                        "usage": store.usage(args.id),
                    }
                )
            else:
                _print(store.list_runs())
        elif args.command == "serve":
            from .web import serve

            serve(store, config=load_config(args.config), port=args.port)
        elif args.command == "tui":
            from .tui import run_tui

            run_tui(store, config_path=args.config, run_id=args.run_id)
        elif args.command == "pause":
            engine.pause(args.id)
            print("Pause requested; an active step will finish at its checkpoint.")
        elif args.command == "resume":
            engine.resume(args.id)
            return _print_run(engine.run(args.id))
        elif args.command == "cancel-experiment":
            _print(engine.cancel_experiment(args.id))
        elif args.command == "intervene":
            _print(engine.intervene(args.id, note=args.note, stage=args.stage))
        elif args.command == "budget":
            _print(
                store.update_budget(
                    args.id,
                    usd=args.usd,
                    max_calls=args.calls,
                    max_experiments=args.experiments,
                    wall_seconds=args.wall_seconds,
                ).budget
            )
        elif args.command == "export":
            store.export_run(args.id, args.target, include_private=args.include_private)
            print(f"Export written to {args.target}")
        return 0
    except KeyboardInterrupt:
        print("Interrupted. Resume from the last completed checkpoint.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"autoresearch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
