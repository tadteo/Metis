"""Human-oriented setup with scriptable settings operations."""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .settings import (
    FIELDS,
    GUIDE,
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
        expected = {"show": 0, "check": 0, "import": 1, "set": 2}[args.action]
        if len(values) != expected:
            raise ValueError(
                f"settings {args.action} expects {expected} arguments; see settings --help"
            )
        if args.action == "show":
            print(config.model_dump_json(indent=2))
            return 0
        if args.action == "import":
            from pathlib import Path

            config = load_config(Path(values[0]).expanduser())
        if args.action == "set":
            data = config.model_dump(mode="json")
            set_value(data, values[0], json.loads(values[1]))
            config = validate_settings(data)
        if args.action == "check":
            report = preflight(config, probe_runtime=True)
            print(json.dumps(report, indent=2))
            return 0 if report["ready"] else 2
        save_settings(store, config, revision)
        print(
            "Settings saved for future runs. Run autoresearch settings check for missing prerequisites."
        )
        return 0
    if args.config:
        config = load_config(args.config)
    if args.check:
        report = preflight(config, probe_runtime=True)
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 2
    print(GUIDE)
    if not sys.stdin.isatty():
        print(
            "Interactive setup needs a terminal. Use setup --check, settings import FILE, or settings set PATH JSON_VALUE.",
            file=sys.stderr,
        )
        return 2
    print("Configure live research. Enter keeps the shown value; :clear empties a text field.")
    print(
        "Ctrl+C cancels without saving. Advanced settings: autoresearch settings set PATH JSON_VALUE."
    )
    config.mode = "live"
    values = {}
    try:
        for field in FIELDS:
            print(f"\n{field.label} — {field.help}")
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
                for index, field in enumerate(FIELDS, 1):
                    print(f"{index}. {field.label}")
                selection = input("Field number to correct (or q to cancel): ").strip()
                if selection.lower() == "q":
                    print("Settings were not saved.")
                    return 2
                if not selection.isdigit() or not 1 <= int(selection) <= len(FIELDS):
                    print("Choose a listed field number.")
                    continue
                field = FIELDS[int(selection) - 1]
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
    print(
        "Next: autoresearch tui or autoresearch serve. Create a run, then explicitly Start / resume."
    )
    return 0
