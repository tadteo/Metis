"""Shared private new-run defaults and guided setup, independent of execution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import ResearchConfig
from .store import ConflictError, Store

GUIDE = """Metis welcomes you.
What question brings you here?

Here, questions become experiments. Evidence guides the next question.
Uncertainty and unsuccessful attempts remain part of the record.

1. Learn the workflow
Bring a research question and, optionally, papers and existing code or data.
Agents inspect limitations, propose ideas, run experiments, compare measured results,
and draft and review a manuscript. Failed attempts stay in the research history.

2. Choose how to begin
Offline demo uses scripted agents and synthetic data, with no API key required.
Live research uses your model account, benchmark and execution environment.
Start with the demo to learn the controls; it is not evidence of research quality.

3. Prepare model access in Settings
Configure a model endpoint, key reference, execution backend and model spending limit.
The initial agent discovers relevant literature and inspects any existing project.
Baseline agents build code, commands and measurement from the sourced task. All
preparation belongs to the same run and model budget. No experiment setup form is needed.
Docker needs a prepared image with dependencies; datasets are mounted read-only.
Local execution requires explicit opt-in. Slurm runs from a configured cluster host.
Manuscript stages also require the pinned PaperOrchestra writer, credentials and TeX;
see docs/paper-orchestra.md. Advanced JSON exposes all writer and routing settings.

4. Check, save, then create
Check setup lists missing prerequisites and untested services. Save incomplete
settings and return later. Settings are private defaults for FUTURE runs; existing
runs retain their recorded configuration. Explicit --config files take precedence.
Set API keys in the launching process environment, then restart the interface.
Do not paste secret values into configuration. No .env file is loaded automatically.

5. Stay in control
Creating a run saves its source and configuration without starting model calls.
Start / resume executes work; Step runs one checkpoint; Pause waits for the current
checkpoint. Inspect Experiments for measurements, Activity for decisions and costs,
and Manuscript / Artifacts for outputs. Saved runs can be resumed after restarting.
Budget limits cover model calls, not cluster, storage or other external costs.
Private state includes source, prompts and results; review exports before sharing.
"""


@dataclass(frozen=True)
class SetupField:
    path: str
    label: str
    help: str
    kind: str = "text"
    choices: tuple[str, ...] = ()


FIELDS = (
    SetupField(
        "project.source_dir",
        "Project · Source directory",
        "Existing absolute source path on the execution host.",
    ),
    SetupField(
        "project.baseline_argv",
        "Project · Baseline command",
        'JSON arguments, e.g. ["python3", "train.py"]. No shell expansion.',
        "json",
    ),
    SetupField(
        "project.evaluator_argv",
        "Project · Evaluator command",
        'JSON arguments, e.g. ["python3", "evaluate.py"]. Writes metrics.json.',
        "json",
    ),
    SetupField(
        "project.protected_paths",
        "Project · Protected evaluator paths",
        'JSON paths relative to source, e.g. ["evaluate.py"].',
        "json",
    ),
    SetupField(
        "project.primary_metric",
        "Project · Primary metric",
        "Must appear in the metrics mapping below.",
    ),
    SetupField(
        "project.metrics",
        "Project · Metrics and direction",
        'JSON mapping, e.g. {"score": "max"}; use min for lower is better.',
        "json",
    ),
    SetupField(
        "project.sota",
        "Project · Published benchmark values",
        'JSON mapping, e.g. {"score": 0.8}; original full-benchmark values.',
        "json",
    ),
    SetupField(
        "project.specification",
        "Data · Research protocol",
        "Describe datasets, fixed splits, outputs, evaluation rules and constraints.",
    ),
    SetupField(
        "project.dataset_manifest",
        "Data · Provenance",
        "JSON mapping of dataset sources / checksums. sha256:path entries are verified.",
        "json",
    ),
    SetupField(
        "execution.readonly_mounts",
        "Data · Docker dataset directories",
        "JSON mapping of mount names to absolute host directories; available as /data/name.",
        "json",
    ),
    SetupField(
        "provider.model",
        "Model · Model identifier",
        "Exact identifier served by your provider; availability is not tested.",
    ),
    SetupField(
        "provider.base_url",
        "Model · API base URL",
        "Compatible API endpoint; remote endpoints require HTTPS.",
    ),
    SetupField(
        "provider.api_key_env",
        "Model · Credential variable",
        "Credential lookup name only. Save its key in Model access or set it in the server environment.",
    ),
    SetupField(
        "execution.backend",
        "Execution · Backend",
        "Docker isolates generated code. Slurm requires a cluster login host.",
        "choice",
        ("docker", "slurm", "local"),
    ),
    SetupField(
        "execution.docker_image",
        "Execution · Docker image",
        "Prepare an image containing your dependencies before starting.",
    ),
    SetupField(
        "execution.slurm_partition",
        "Execution · Slurm partition",
        "Optional cluster partition; ignored by other backends.",
    ),
    SetupField(
        "execution.slurm_account",
        "Execution · Slurm account",
        "Optional cluster account; ignored by other backends.",
    ),
    SetupField(
        "execution.allow_local",
        "Execution · Allow local code",
        "Explicitly permit generated code to run with your user permissions.",
        "bool",
    ),
    SetupField(
        "budget.usd",
        "Limits · Model cost (USD)",
        "Total per-run limit; compute and storage costs are separate.",
        "number",
    ),
    SetupField("budget.max_calls", "Limits · Model calls", "Maximum calls per run.", "integer"),
    SetupField(
        "budget.max_experiments", "Limits · Experiments", "Maximum experiments per run.", "integer"
    ),
    SetupField(
        "budget.wall_seconds",
        "Limits · Duration (seconds)",
        "Measured from run creation, including paused time.",
        "integer",
    ),
    SetupField(
        "privacy.traces",
        "Privacy · Diagnostic traces",
        "All run state stays private; this controls duplicate diagnostics.",
        "choice",
        ("redacted", "metadata", "full"),
    ),
    SetupField(
        "privacy.cache",
        "Privacy · Cache model responses",
        "Persistent private response reuse.",
        "bool",
    ),
)


def get_value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split("."):
        value = value[key]
    return value


def set_value(data: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    target = data
    for key in keys[:-1]:
        if key not in target or not isinstance(target[key], dict):
            raise ValueError("Unknown settings path: " + path)
        target = target[key]
    if keys[-1] not in target:
        raise ValueError("Unknown settings path: " + path)
    target[keys[-1]] = value


def field_text(data: dict[str, Any], field: SetupField) -> str:
    value = get_value(data, field.path)
    return json.dumps(value) if field.kind in {"json", "bool"} else str(value)


def apply_fields(config: ResearchConfig, values: dict[str, str]) -> ResearchConfig:
    data = config.model_dump(mode="json")
    for field in FIELDS:
        if field.path not in values:
            continue
        raw = values[field.path]
        try:
            value = json.loads(raw) if field.kind in {"json", "bool", "number", "integer"} else raw
        except ValueError as exc:
            raise ValueError(f"{field.label}: enter valid {field.kind} data.") from exc
        set_value(data, field.path, value)
    return validate_settings(data)


def validate_settings(data: dict[str, Any]) -> ResearchConfig:
    config = ResearchConfig.model_validate(data)

    # Credentials are references, including optional providers and native writer keys.
    def check(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("api_key_env") and (
                    not isinstance(item, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item)
                ):
                    raise ValueError(
                        f"{key} must be an environment variable name, never a secret value"
                    )
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(config.model_dump(mode="json"))
    return config


def load_settings(store: Store) -> tuple[ResearchConfig, int]:
    from .model_settings import snapshot

    with store.connect() as db:
        row = db.execute("SELECT config FROM settings WHERE id=1").fetchone()
    config = ResearchConfig.model_validate_json(row[0]) if row else ResearchConfig()
    project = config.project.source_dir or ""
    current = snapshot(store, "project" if project else "workspace", project)
    return ResearchConfig.model_validate(current["config"]), current["settings_revision"]


def save_settings(store: Store, config: ResearchConfig, revision: int) -> int:
    from .model_settings import _row, _snapshot, _write, global_store, select_models

    config = validate_settings(config.model_dump(mode="json"))
    config.mode = "live"
    with global_store().connect() as global_db:
        global_db.execute("BEGIN IMMEDIATE")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            legacy = db.execute("SELECT config,revision FROM settings WHERE id=1").fetchone()
            old = ResearchConfig.model_validate_json(legacy[0]) if legacy else ResearchConfig()
            project = old.project.source_dir or ""
            before = _snapshot(db, global_db, "project" if project else "workspace", project)
            if before["settings_revision"] != revision:
                raise ConflictError(
                    "Settings changed in another interface. Reload settings before saving again."
                )
            previous_models = select_models(ResearchConfig.model_validate(before["config"]))
            changed_models = {
                key: value
                for key, value in select_models(config).items()
                if value != previous_models[key]
            }
            current = _row(db, "workspace")
            overrides = current[0] if current else select_models(old) if legacy else {}
            _write(db, "workspace", {**overrides, **changed_models})
            db.execute(
                "INSERT OR REPLACE INTO settings(id,config,revision) VALUES(1,?,?)",
                (config.model_dump_json(), (legacy[1] if legacy else 0) + 1),
            )
            project = config.project.source_dir or ""
            return int(
                _snapshot(db, global_db, "project" if project else "workspace", project)[
                    "settings_revision"
                ]
            )
