"""Human-oriented setup with scriptable settings operations."""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .model_profiles import apply_model_profile
from .settings import (
    FIELDS,
    apply_fields,
    field_text,
    load_settings,
    save_settings,
    set_value,
    validate_settings,
)
from .setup import preflight
from .store import Store


def configure(args: argparse.Namespace) -> int:
    store = Store(args.state_dir, db_dir=getattr(args, "db_dir", None))
    config, revision = load_settings(store)
    if args.command == "settings":
        values = args.values
        expected = {"show": 0, "check": 0, "import": 1, "set": 2, "profile": 1, "inherit": 0}[
            args.action
        ]
        if len(values) != expected:
            raise ValueError(
                f"settings {args.action} expects {expected} arguments; see settings --help"
            )
        if args.scope:
            return _model_settings(args, store)
        if args.action == "inherit":
            raise ValueError("Choose --scope workspace or --scope project to restore inheritance")
        if args.action == "show":
            print(config.model_dump_json(indent=2))
            return 0
        if args.action == "import":
            from pathlib import Path

            config = load_config(Path(values[0]).expanduser())
        if args.action == "profile":
            config = apply_model_profile(config, values[0])
        if args.action == "set":
            data = config.model_dump(mode="json")
            set_value(data, values[0], json.loads(values[1]))
            config = validate_settings(data)
        if args.action == "check":
            report = preflight(config, probe_runtime=True)
            print(json.dumps(report, indent=2))
            return 0 if report["ready"] else 2
        save_settings(store, config, revision)
        print("Settings saved for future runs. Run metis settings check for missing prerequisites.")
        return 0
    if args.config:
        config = load_config(args.config)
    if args.check:
        report = preflight(config, probe_runtime=True)
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 2
    print("METIS / FIRST STEPS\nProject → Models → Execution → Limits → Privacy\n")
    if not sys.stdin.isatty():
        print(
            "Interactive setup needs a terminal. Use setup --check, settings import FILE, or settings set PATH JSON_VALUE.",
            file=sys.stderr,
        )
        return 2
    print("Configure live research. Enter keeps the shown value; :clear empties a text field.")
    print("Ctrl+C cancels without saving. Advanced settings: metis settings set PATH JSON_VALUE.")
    config.mode = "live"
    if not args.config:
        config.entry_mode = "agent"
    fields = [
        field
        for field in FIELDS
        if config.entry_mode == "configured"
        or not field.path.startswith("project.")
        or field.path == "project.source_dir"
    ]
    values = {}
    try:
        section = ""
        step = 0
        for field in fields:
            group, _, label = field.label.partition(" · ")
            if group != section:
                section = group
                step += 1
                print(f"\n{step:02d} / {section.upper()}\n")
            print(f"{label or field.label} — {field.help}")
            current = field_text(config.model_dump(mode="json"), field)
            while True:
                choices = f" ({', '.join(field.choices)})" if field.choices else ""
                answer = input(f"[{current}]{choices} > ").strip()
                raw = "" if answer == ":clear" else (answer or current)
                try:
                    if field.kind in {"json", "bool", "number", "integer"}:
                        json.loads(raw)
                    if field.choices and raw not in field.choices:
                        raise ValueError("Choose one of the listed options")
                except ValueError:
                    print(f"Invalid {field.kind} value. Try again; earlier answers are retained.")
                    continue
                values[field.path] = raw
                break
        while True:
            try:
                config = apply_fields(config, values)
                break
            except ValueError as exc:
                print(f"Settings need correction: {exc}")
                for index, field in enumerate(fields, 1):
                    print(f"{index}. {field.label}")
                selection = input("Field number to correct (or q to cancel): ").strip()
                if selection.lower() == "q":
                    print("Settings were not saved.")
                    return 2
                if not selection.isdigit() or not 1 <= int(selection) <= len(fields):
                    print("Choose a listed field number.")
                    continue
                field = fields[int(selection) - 1]
                values[field.path] = (
                    input(f"{field.label} [{values[field.path]}] > ").strip() or values[field.path]
                )
        report = preflight(config, probe_runtime=True)
        for check in report["checks"]:
            print(f"{check['status'].upper()}: {check['name']}: {check['message']}")
        if input("Save these settings for future runs? [Y/n] ").strip().lower() not in {
            "",
            "y",
            "yes",
        }:
            print("Settings were not saved.")
            return 0
    except EOFError:
        print("Input ended. Settings were not saved.", file=sys.stderr)
        return 2
    save_settings(store, config, revision)
    print(
        "Settings saved."
        + (
            " Local checks passed."
            if report["ready"]
            else " Setup is incomplete; resolve the checks above."
        )
    )
    print("Next: metis tui or metis serve. Create a run, then explicitly Start / resume.")
    return 0


def _model_settings(args: argparse.Namespace, store: Store) -> int:
    from pathlib import Path

    from . import model_settings
    from .config import ResearchConfig

    current = model_settings.snapshot(store, args.scope, args.project)
    config = ResearchConfig.model_validate(current["config"])
    if args.action == "show":
        print(json.dumps(current, indent=2))
        return 0
    if args.action == "check":
        report = preflight(config, probe_runtime=True)
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 2
    overrides = dict(current["overrides"])
    if args.action == "inherit":
        overrides = {}
    elif args.action == "import":
        overrides = model_settings.validate_models(json.loads(Path(args.values[0]).read_text()))
    else:
        before = model_settings.select_models(config)
        if args.action == "profile":
            config = apply_model_profile(config, args.values[0])
        else:
            if args.values[0].split(".")[0] not in model_settings.MODEL_KEYS:
                raise ValueError("This scope contains only model routing and Laya settings")
            data = config.model_dump(mode="json")
            set_value(data, args.values[0], json.loads(args.values[1]))
            config = validate_settings(data)
        after = model_settings.select_models(config)
        overrides.update({key: value for key, value in after.items() if value != before[key]})
    model_settings.save_scope(store, args.scope, args.project, overrides, current["revision"])
    print(f"{args.scope.capitalize()} model settings saved for future runs.")
    return 0
