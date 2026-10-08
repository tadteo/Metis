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
        if args.action == "preset":
            return _preset(args, store, config, revision)
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


def _preset(args: argparse.Namespace, store: Store, config: object, revision: int) -> int:
    """List or add published provider presets. Keys go only to the host vault."""
    from . import credentials, model_settings, provider_presets
    from .config import ResearchConfig
    from .model_inventory import initial_inventory

    values = list(args.values)
    command = values[0] if values else "list"
    if command not in {"list", "show", "add"} or len(values) != (1 if command == "list" else 2) - (
        0 if values else 1
    ):
        raise ValueError("settings preset expects: list | show PROVIDER:MODEL | add PROVIDER:MODEL")
    catalog = provider_presets.load_catalog()
    if command == "list":
        view = provider_presets.catalog_view(catalog)
        if args.json:
            print(json.dumps(view, indent=2))
            return 0
        print(f"METIS / PROVIDER PRESETS  ·  catalog {view['catalog_version']}")
        print("Published figures with sources; no provider request was made.\n")
        for provider in view["providers"]:
            key = provider["api_key_env"] if provider["key_required"] else "no key needed"
            print(f"{provider['label']}  ·  {provider['base_url']}  ·  {key}")
            if provider["data_use"]:
                print(f"  Data use: {provider['data_use']}")
            for model in provider["models"]:
                print(f"  {model['reference']}")
                print(f"    {_price(model)}  ·  {model['limits']}")
            if provider["custom_models"]:
                print(f"  {provider['id']}:MODEL-ID  (any model your server serves)")
            print()
        print("Add one: metis settings preset add PROVIDER:MODEL")
        return 0
    provider, model = provider_presets.find(values[1], catalog)
    summary = provider_presets.summary(provider, model)
    if command == "show":
        print(json.dumps(summary, indent=2) if args.json else _describe(summary))
        return 0
    entry = provider_presets.to_entry(
        provider,
        model,
        catalog_version=catalog.catalog_version,
        base_url=(args.base_url or None) if provider.custom_models else None,
    )
    if args.base_url and not provider.custom_models:
        raise ValueError("--base-url applies only to the local compatible server preset")
    if args.scope:
        current = model_settings.snapshot(store, args.scope, args.project)
        scoped = ResearchConfig.model_validate(current["config"])
        inventory = provider_presets.add_to_inventory(
            scoped.model_inventory or initial_inventory(scoped), entry
        )
        overrides = {**current["overrides"], "model_inventory": inventory.model_dump(mode="json")}
        model_settings.save_scope(store, args.scope, args.project, overrides, current["revision"])
        where = f"{args.scope} model settings"
    else:
        assert isinstance(config, ResearchConfig)
        config.model_inventory = provider_presets.add_to_inventory(
            config.model_inventory or initial_inventory(config), entry
        )
        save_settings(store, config, revision)
        where = "Available to Metis"
    print(f"{entry.label} added to {where} for future runs.")
    print(_describe(summary))
    if not provider.key_required:
        print("No key needed for a loopback server. Start that server before research.")
        return 0
    name = provider.api_key_env
    if not args.no_key:
        source = credentials.status(name)["source"]
        if source != "missing":
            print(f"A key for {name} is available from the {source}.")
            return 0
    if args.no_key or not sys.stdin.isatty():
        print(
            f"Key needed: add {name} in Settings → Model access, or set it in the server environment."
        )
        return 0
    import getpass

    secret = getpass.getpass(f"Paste your {name} key (hidden; Enter to skip): ").strip()
    if not secret:
        print(f"Key needed: add {name} later in Settings → Model access.")
        return 0
    if not credentials.vault_available():
        print(
            f"No host credential vault is available. Set {name} in the environment of the "
            "process that runs Metis, or add it in the browser for the current server session."
        )
        return 0
    credentials.save(name, secret, "vault")
    print(f"Key saved in this host's credential vault as {name}. It is not written to settings.")
    return 0


def _price(model: dict[str, object]) -> str:
    inp, out = model["input_per_million"], model["output_per_million"]
    if inp is None or out is None:
        return "price not published"
    return f"${inp:g} / ${out:g} per million tokens (input / output)"


def _describe(summary: dict[str, object]) -> str:
    def known(value: object, unit: str = "") -> str:
        return (
            "not published"
            if value is None
            else f"{value:,}{unit}"
            if isinstance(value, int) and not isinstance(value, bool)
            else str(value)
        )

    lines = [
        f"{summary['label']}  ({summary['reference']})",
        f"  Endpoint: {summary['base_url']}",
        "  Key variable: "
        + (str(summary["api_key_env"]) if summary["key_required"] else "none (loopback server)"),
        f"  Context window: {known(summary['context_window'], ' tokens')}",
        f"  Max output: {known(summary['max_output_tokens'], ' tokens')}",
        f"  Price: {_price(summary)}",
        f"  {summary['limits']}",
    ]
    if summary["data_use"]:
        lines.append(f"  Data use: {summary['data_use']}")
    if summary["capability"]:
        lines.append(f"  Provider description (not measured by Metis): {summary['capability']}")
    notes = [*summary["notes"], *summary["provider_notes"]]  # type: ignore[misc]
    lines += [f"  Note: {note}" for note in notes]
    return "\n".join(lines)
