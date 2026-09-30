"""Small, scriptable CLI for the same engine used by the research console."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
import webbrowser
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
        prog="metis",
        description="Metis · Research atelier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Start here: setup → tui / serve → new → run\nInspect: status · system · fidelity\nManage: settings · theme · pause · resume · budget · export",
    )
    parser.add_argument(
        "--state-dir", type=Path, help="Private runtime root (or AUTORESEARCH_HOME)"
    )
    parser.add_argument(
        "--db-dir", type=Path, help="Separate SQLite directory (or AUTORESEARCH_DB_DIR)"
    )
    commands = parser.add_subparsers(dest="command", title="Commands", metavar="COMMAND")
    theme = commands.add_parser("theme", help="Choose the shared charcoal / cream appearance")
    theme.add_argument("name", choices=["charcoal", "cream"], nargs="?")
    setup = commands.add_parser("setup", help="Guided first-time setup (no research execution)")
    setup.add_argument("--config", type=Path, help="Start from an existing configuration")
    setup.add_argument(
        "--check", action="store_true", help="Print readiness without interactive prompts"
    )
    settings = commands.add_parser("settings", help="Manage private defaults for future runs")
    settings.add_argument(
        "action",
        choices=["show", "import", "set", "check", "profile", "inherit"],
        nargs="?",
        default="show",
    )
    settings.add_argument(
        "values", nargs="*", help="import FILE, set DOTTED.PATH JSON_VALUE, or profile google-flash"
    )
    settings.add_argument(
        "--scope",
        choices=["global", "workspace", "project"],
        help="Edit inherited model defaults only",
    )
    settings.add_argument(
        "--project", default="", help="Absolute project path for project model overrides"
    )
    init = commands.add_parser("init", help="Write an example configuration")
    init.add_argument("path", type=Path, nargs="?", default=Path("autoresearch.example.json"))
    init.add_argument("--demo", action="store_true", help="Configure offline demonstration mode")
    new = commands.add_parser("new", help="Create a research run")
    new.add_argument("--title", default="")
    new.add_argument("--objective", required=True)
    new.add_argument("--config", type=Path)
    new.add_argument("--demo", action="store_true")
    new.add_argument(
        "--paper",
        action="append",
        default=[],
        help="Associated PDF/text file, URL, DOI or arXiv ID; repeatable",
    )
    new.add_argument(
        "--project", default="", help="Optional existing project folder; copied privately"
    )
    new.add_argument("--budget", type=float, help="One model budget including research intake")
    new.add_argument(
        "--configured", action="store_true", help="Use imported legacy experiment configuration"
    )
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
    status.add_argument(
        "--json", action="store_true", help="Full machine-readable output (automatic in pipes)"
    )
    web = commands.add_parser("serve", help="Open the local web console")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--config", type=Path)
    commands.add_parser("fidelity", help="Validate and print the fidelity evidence matrix")
    system = commands.add_parser(
        "system", help="Inspect agents, prompts, routing and the workflow without model calls"
    )
    system.add_argument("--config", type=Path)
    system.add_argument(
        "--run", dest="run_id", help="Inspect the frozen definitions of an existing run"
    )
    system.add_argument("--role", help="Inspect one agent and its resolved instructions")
    system.add_argument(
        "--mermaid", action="store_true", help="Print the executable workflow as a Mermaid graph"
    )
    validate = commands.add_parser(
        "validate-specs", help="Validate the AI specification bundle without execution"
    )
    validate.add_argument("--config", type=Path)
    adopt = commands.add_parser(
        "adopt-behavior", help="Explicitly bind an unpinned legacy run to current AI behavior"
    )
    adopt.add_argument("id")
    evaluation = commands.add_parser(
        "evaluate", help="Prepare, baseline, run or inspect real public research tasks"
    )
    evaluation.add_argument("action", choices=["prepare", "baseline", "run", "report", "variants"])
    evaluation.add_argument("directory", type=Path)
    evaluation.add_argument("--config", type=Path)
    evaluation.add_argument("--reference-config", type=Path)
    evaluation.add_argument("--variant", default="configured")
    evaluation.add_argument("--steps", type=int)
    tui = commands.add_parser("tui", help="Open the interactive terminal research console")
    tui.add_argument("--config", type=Path, help="Load configuration for new research projects")
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
    remote = commands.add_parser(
        "remote", help="Manage SSH research controllers and private tunnels"
    )
    remote_commands = remote.add_subparsers(dest="remote_command", required=True)
    remote_commands.add_parser("hosts", help="List discovered SSH configuration hosts")
    remote_commands.add_parser("list", help="List saved remote profiles")
    add = remote_commands.add_parser(
        "add", help="Save a remote profile; does not connect or install"
    )
    add.add_argument("name")
    add.add_argument("--host", required=True, help="SSH alias, hostname or user@hostname")
    add.add_argument("--port", type=int, help="SSH port; otherwise use SSH configuration")
    add.add_argument("--identity-file", help="Local SSH identity path (never a password)")
    add.add_argument("--directory", default="~/.local/share/autoresearch/remote")
    add.add_argument("--python", default="python3")
    add.add_argument(
        "--remote-state-dir",
        dest="remote_state_dir",
        help="Remote research files and experiment workspaces (for example project storage)",
    )
    add.add_argument(
        "--remote-db-dir",
        dest="remote_db_dir",
        help="Controller SQLite directory on persistent host-local storage",
    )
    add.add_argument("--remote-config", dest="remote_config")
    for action, help_text in {
        "login": "Sign in through interactive SSH, including MFA",
        "check": "Probe SSH and remote readiness without installing",
        "install": "Explicitly install the remote research runtime",
        "connect": "Start/reuse the remote controller and keep its tunnel open",
        "status": "Inspect remote controller/tunnel status",
        "disconnect": "Disconnect a managed local tunnel; remote research continues",
    }.items():
        command = remote_commands.add_parser(action, help=help_text)
        command.add_argument("name")
        if action == "connect":
            command.add_argument(
                "--open", action="store_true", help="Open the private dashboard in a browser"
            )
    return parser


def _remote_manager(root: Path) -> Any:
    from .remote import RemoteManager

    return RemoteManager(root=root)


def _remote_profile(**values: Any) -> Any:
    from .remote import RemoteProfile

    return RemoteProfile(**values)


def _remote_result(result: dict[str, Any]) -> int:
    # Authenticated access links belong only to explicit connect output.
    _print({key: value for key, value in result.items() if key not in {"url", "token"}})
    return (
        2
        if result.get("status") in {"failed", "error", "not_installed", "unavailable", "expired"}
        or result.get("ready") is False
        else 0
    )


def _remote_login(manager: Any, name: str) -> int:
    session_id = ""
    previous = ""
    status: Any = None
    try:
        result = manager.authenticate(name)
        while True:
            session_id = str(result.get("session_id", session_id))
            output = str(result.get("output", ""))
            fresh = output[len(previous) :] if output.startswith(previous) else output
            if fresh:
                print(fresh, end="" if fresh.endswith("\n") else "\n", file=sys.stderr, flush=True)
            previous = output
            status = result.get("status")
            if status != "authenticating":
                print(str(result.get("message") or status), file=sys.stderr)
                return 0 if status == "authenticated" else 2
            # The broker can explicitly signal a prompt; otherwise recognize the
            # normal password, host-key and keyboard-interactive SSH delimiters.
            prompt = output.rstrip().endswith((":", "?", ")", "]"))
            if result.get("awaiting_input") or (fresh and prompt):
                answer = getpass.getpass("SSH response (hidden): ")
                try:
                    result = manager.answer_authentication(session_id, answer)
                except Exception as error:
                    message = str(error).replace(answer, "[redacted]") if answer else str(error)
                    raise RuntimeError(message) from None
                finally:
                    answer = ""
            else:
                time.sleep(0.2)
                result = manager.authentication(session_id)
    finally:
        if session_id and status != "authenticated":
            manager.cancel_authentication(session_id)


def _remote_command(args: argparse.Namespace, store: Store) -> int:
    manager = _remote_manager(store.root)
    try:
        action = args.remote_command
        if action in {"check", "install", "connect"}:
            # MFA belongs to the same manager lifetime as the requested action.
            # The manager-owned SSH master intentionally closes at command exit.
            authenticated = _remote_login(manager, args.name)
            if authenticated:
                return authenticated
        if action == "hosts":
            _print(manager.hosts())
        elif action == "list":
            _print(manager.profiles())
        elif action == "add":
            profile = _remote_profile(
                name=args.name,
                host=args.host,
                port=args.port,
                identity_file=args.identity_file,
                directory=args.directory,
                python=args.python,
                state_dir=args.remote_state_dir,
                db_dir=args.remote_db_dir,
                config_path=args.remote_config,
            )
            return _remote_result(manager.save_profile(profile))
        elif action == "login":
            result_code = _remote_login(manager, args.name)
            if result_code == 0:
                print(
                    "Sign-in verified. This test closes its SSH session on exit; check, install and connect sign in within their own session.",
                    file=sys.stderr,
                )
            return result_code
        elif action == "connect":
            result = manager.connect(args.name)
            if result.get("status") != "connected" or not result.get("url"):
                return _remote_result(result) or 2
            _print(result)  # Intentional private access link requested by the user.
            if args.open:
                webbrowser.open(str(result["url"]))
            print(
                "Tunnel active. Keep this command open; Ctrl+C disconnects it. Remote research continues.",
                file=sys.stderr,
                flush=True,
            )
            try:
                while True:
                    time.sleep(1)
                    result = manager.status(args.name)
                    if result.get("status") not in {"connected", "reconnecting"}:
                        return _remote_result(result) or 2
            except KeyboardInterrupt:
                print("Tunnel disconnected. Remote research continues.", file=sys.stderr)
                return 0
            finally:
                manager.disconnect(args.name)
        else:
            method = manager.probe if action == "check" else getattr(manager, action)
            return _remote_result(method(args.name))
        return 0
    finally:
        manager.close()


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        from .terminal_style import WELCOME

        print(WELCOME)
        return 0
    if getattr(args, "steps", None) is not None and args.steps < 1:
        parser.error("--steps must be positive")
    try:
        if args.command in {"setup", "settings"}:
            from .setup_cli import configure

            return configure(args)
        if args.command == "init":
            if args.path.exists():
                raise ValueError(f"Refusing to overwrite existing configuration: {args.path}")
            save_example(args.path, demo=args.demo)
            print(f"Configuration written to {args.path}")
            return 0
        if args.command == "fidelity":
            from .fidelity import load_matrix

            _print(load_matrix())
            return 0
        if args.command == "check":
            from .setup import preflight

            report = preflight(load_config(args.config), probe_runtime=True)
            _print(report)
            return 0 if report["ready"] else 2
        if args.command in {"system", "validate-specs"}:
            from .behavior import describe, inspect_run
            from .catalog import load_catalog
            from .system_view import mermaid

            config = load_config(args.config)
            if getattr(args, "run_id", None):
                store = Store(args.state_dir, db_dir=args.db_dir)
                info = inspect_run(store, store.get_run(args.run_id))
            else:
                info = describe(config)
            if args.command == "validate-specs":
                _print(
                    {
                        "valid": True,
                        "agents": len(info["agents"]),
                        "stages": len(info["workflow"]["nodes"]),
                        "catalog_sha256": info["catalog_sha256"],
                        "workflow_sha256": info["workflow_sha256"],
                    }
                )
            elif args.mermaid:
                print(mermaid(info["workflow"]))
            elif args.role:
                if args.role not in info["agents"]:
                    raise ValueError("unknown agent role: " + args.role)
                if args.run_id:
                    prompt = info["prompts"][args.role]
                else:
                    catalog = load_catalog(
                        Path(config.specification_dir) if config.specification_dir else None
                    )
                    prompt = catalog.render(args.role, config.prompt_overrides.get(args.role, ""))
                _print({"agent": info["agents"][args.role], "prompt": prompt})
            else:
                _print(info)
            return 0
        store = Store(args.state_dir, db_dir=args.db_dir)
        if args.command == "remote":
            return _remote_command(args, store)
        if args.command == "theme":
            from .appearance import load_theme, save_theme

            name = save_theme(store, args.name) if args.name else load_theme(store)
            print(f"Metis appearance: {name}")
            return 0
        engine = Engine(store)
        from .settings import load_settings

        defaults = (
            load_config(args.config) if getattr(args, "config", None) else load_settings(store)[0]
        )
        if args.command == "new":
            from .research_inputs import paper_arguments

            if args.configured:
                defaults.entry_mode = "configured"
            elif not args.config:
                defaults.entry_mode = "agent"
            if args.project:
                defaults.project.source_dir = str(Path(args.project).expanduser().resolve())
            if args.budget is not None:
                defaults.budget.usd = args.budget
            engine = Engine(store, defaults)
            _print(
                engine.create(
                    args.title or args.objective[:100],
                    args.objective,
                    demo=args.demo,
                    papers=paper_arguments(args.paper),
                )
            )
        elif args.command == "run":
            return _print_run(engine.run(args.id, max_steps=args.steps))
        elif args.command == "demo":
            state = engine.create(args.title, args.objective, demo=True)
            print(f"Created demonstration run {state.id}", file=sys.stderr)
            return _print_run(engine.run(state.id, max_steps=args.steps))
        elif args.command == "status":
            value = (
                {
                    "run": store.get_run(args.id).model_dump(mode="json"),
                    "usage": store.usage(args.id),
                }
                if args.id
                else store.list_runs()
            )
            if sys.stdout.isatty() and not args.json:
                from .appearance import load_theme
                from .terminal_style import print_status

                print_status(value, load_theme(store))
            else:
                _print(value)
        elif args.command == "serve":
            from .web import serve

            serve(store, config=load_config(args.config) if args.config else None, port=args.port)
        elif args.command == "tui":
            from .tui import ResearchApp

            if args.run_id:
                store.get_run(args.run_id)
            ResearchApp(
                store, defaults if args.config else None, args.run_id, config_path=args.config
            ).run()
        elif args.command == "evaluate":
            from .evaluation import baseline_suite, prepare_suite, report_suite, run_suite, variants

            config = load_config(args.config)
            reference = load_config(args.reference_config) if args.reference_config else None
            if args.action == "prepare":
                _print(prepare_suite(args.directory, config))
            elif args.action == "baseline":
                result = baseline_suite(args.directory, config.execution if args.config else None)
                _print(result)
                return 0 if result["ready_tasks"] == result["registered_tasks"] else 2
            elif args.action == "run":
                result = run_suite(store, args.directory, args.steps, args.variant, reference)
                _print(result)
                return 2 if result["failed_or_blocked_task_variants"] else 0
            elif args.action == "variants":
                _print(variants(config, reference))
            else:
                _print(report_suite(store, args.directory))
        elif args.command == "adopt-behavior":
            from .behavior import adopt_legacy

            _print(adopt_legacy(store, args.id))
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
