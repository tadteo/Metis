"""Read-only project discovery and separately budgeted, reviewable setup proposals.

Preparation receipts are private and independent of scientific runs. A submitted
proposal is never replayed after an uncertain interruption. Neither discovery nor
proposal generation executes project code or changes a research configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from typing import Any

from pydantic import Field, JsonValue, field_validator

from .catalog import load_catalog
from .config import ResearchConfig
from .contracts import AgentOutput, AgentRequest, Model, Usage
from .privacy import redact
from .providers import CompatibleProvider, ProviderError
from .runtime_support import relative_parts
from .settings import set_value, validate_settings
from .source_policy import source_is_excluded
from .store import Store

MAX_FILES = 1200
MAX_DOCUMENTS = 35
MAX_BYTES = 90000
SKIP_DIRS = {
    "outputs",
    "logs",
    "checkpoints",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
ALLOWED_FIELDS = {
    "project.baseline_argv",
    "project.evaluator_argv",
    "project.protected_paths",
    "project.include",
    "project.metrics",
    "project.primary_metric",
    "project.sota",
    "project.baseline_expected",
    "project.specification",
    "project.dataset_manifest",
    "project.seeds",
    "project.experiment_timeout",
    "execution.backend",
    "execution.docker_image",
    "execution.slurm_partition",
    "execution.slurm_account",
}


class Suggestion(Model):
    field: str
    value: JsonValue
    reason: str = Field(min_length=1, max_length=3000)
    evidence: list[str] = Field(min_length=1, max_length=20)

    @field_validator("field")
    @classmethod
    def supported(cls, value: str) -> str:
        if value not in ALLOWED_FIELDS:
            raise ValueError("Unsupported setup field")
        return value


class DraftFile(Model):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=30000)
    purpose: str = Field(min_length=1, max_length=2000)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        relative_parts(value)
        if source_is_excluded(value):
            raise ValueError("Draft targets a private or excluded path")
        return value


class Proposal(Model):
    summary: str = Field(min_length=1, max_length=5000)
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=30)
    questions: list[str] = Field(default_factory=list, max_length=15)
    blockers: list[str] = Field(default_factory=list, max_length=15)
    drafts: list[DraftFile] = Field(default_factory=list, max_length=6)


def read_project_excerpt(root: Path, relative: str, limit: int) -> str | None:
    path = root / relative
    try:
        if any(parent.is_symlink() for parent in [path, *path.parents]):
            return None
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return None
            data = stream.read(limit + 1)
        if b"\x00" in data:
            return None
        text = data[:limit].decode("utf-8")
        return text + ("\n[File excerpt truncated]" if len(data) > limit else "")
    except (OSError, UnicodeError):
        return None


def inspect_project(source_dir: str) -> dict[str, Any]:
    if not source_dir.strip():
        raise ValueError("Choose a project folder first.")
    root = Path(source_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Project folder does not exist on the machine running Metis.")
    files: list[str] = []
    truncated = False
    visited = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if not (Path(directory) / d).is_symlink()
            and not source_is_excluded((Path(directory) / d).relative_to(root))
            and d not in SKIP_DIRS
            and not d.startswith(".")
        )
        visited += len(dirs) + len(names)
        if visited > 10000:
            truncated = True
            break
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if source_is_excluded(relative) or path.is_symlink() or not path.is_file():
                continue
            files.append(relative)
            if len(files) >= MAX_FILES:
                truncated = True
                break
        if truncated:
            break

    # Small documentation/configuration/script excerpts; never import the project.
    def priority(name: str) -> tuple[int, str]:
        base = Path(name).name.lower()
        rank = (
            0
            if base in {"readme.md", "agents.md", "pyproject.toml"}
            else 1
            if name.endswith((".sbatch", ".sh"))
            else 2
        )
        return rank, name

    documents: list[dict[str, Any]] = []
    total = 0
    for name in sorted(files, key=priority):
        if not name.endswith((".md", ".toml", ".yaml", ".yml", ".py", ".sh", ".sbatch", ".json")):
            continue
        if len(documents) >= MAX_DOCUMENTS or total >= MAX_BYTES:
            truncated = True
            break
        content = read_project_excerpt(root, name, min(10000, MAX_BYTES - total))
        if content is None:
            continue
        read_limit = min(10000, MAX_BYTES - total)
        total += len(content.encode())
        documents.append(
            {
                "path": name,
                "read_limit": read_limit,
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
                "excerpt": redact(content, preserve_paths=True),
            }
        )
    candidates = {
        role: [f for f in files if Path(f).name in names]
        for role, names in {
            "baseline": {"train.py", "baseline.py", "train.sbatch", "submit_training.sh"},
            "evaluator": {"evaluate.py", "eval.py", "evaluate.sbatch"},
        }.items()
    }
    warnings = [
        "Discovery is read-only. Candidate filenames are not verified commands or measurements."
    ]
    if any(f.endswith(".sbatch") for f in files):
        warnings.append(
            "Scheduler scripts found. Metis's generic Slurm backend does not adopt existing batch scripts or GPU/node/task requests. A compatible execution adapter is required for those launchers; do not nest sbatch inside an experiment."
        )
    if truncated:
        warnings.append(
            "Inspection is bounded and incomplete. Review the excerpts and missing project context before asking AI."
        )
    return {
        "source_dir": str(root),
        "files": files,
        "documents": documents,
        "candidates": candidates,
        "warnings": warnings,
        "truncated": truncated,
    }


def _table(store: Store) -> None:
    with store.connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS setup_proposals (id TEXT PRIMARY KEY, status TEXT NOT NULL, record TEXT NOT NULL)"
        )


def _save(store: Store, record: dict[str, Any]) -> None:
    with store.connect() as db:
        db.execute(
            "UPDATE setup_proposals SET status=?,record=? WHERE id=?",
            (record["status"], json.dumps(record), record["id"]),
        )


def get_proposal(store: Store, proposal_id: str) -> dict[str, Any]:
    _table(store)
    with store.connect() as db:
        row = db.execute(
            "SELECT record,status FROM setup_proposals WHERE id=?", (proposal_id,)
        ).fetchone()
    if row is None:
        raise ValueError("Unknown setup proposal")
    record = dict(json.loads(row[0]))
    record["status"] = row[1]
    return record


def list_proposals(store: Store) -> list[dict[str, Any]]:
    _table(store)
    with store.connect() as db:
        rows = db.execute(
            "SELECT record FROM setup_proposals ORDER BY rowid DESC LIMIT 20"
        ).fetchall()
    return [public_proposal(dict(json.loads(row[0]))) for row in rows]


def public_proposal(record: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: record[key]
        for key in (
            "id",
            "status",
            "source_dir",
            "objective",
            "model",
            "maximum_usd",
            "usage",
            "proposal",
            "error",
            "inspection",
        )
        if key in record
    }
    result["request_preview"] = {
        "destination": record["provider"]["base_url"],
        "model": record["provider"]["model"],
        "system": record["request"]["system"],
        "prompt": json.loads(record["request"]["prompt"]),
        "max_output_tokens": record["provider"]["max_output_tokens"],
        "retries": record["provider"]["retries"],
    }
    return result


def prepare_proposal(
    store: Store, config: ResearchConfig, objective: str, maximum_usd: float
) -> dict[str, Any]:
    if not objective.strip() or len(objective) > 20000:
        raise ValueError("Describe what you want to investigate (up to 20,000 characters).")
    if not 0 < maximum_usd <= 5:
        raise ValueError("Choose an AI preparation limit greater than zero and at most $5.")
    inspection = inspect_project(config.project.source_dir)
    catalog = load_catalog(Path(config.specification_dir) if config.specification_dir else None)
    provider = config.provider.model_copy(
        update={"retries": 0, "max_output_tokens": min(config.provider.max_output_tokens, 6000)}
    )
    request = AgentRequest(
        run_id="setup-" + uuid.uuid4().hex,
        stage="project_setup",
        role="project_setup",
        system=catalog.render("project_setup"),
        prompt=json.dumps(
            redact(
                {
                    "objective": objective,
                    "project": inspection,
                    "current_project_settings": config.project.model_dump(mode="json"),
                    "execution": config.execution.model_dump(mode="json"),
                    "proposal_schema": Proposal.model_json_schema(),
                },
                config.privacy.redact_patterns,
                preserve_paths=True,
            )
        ),
        temperature=0,
    )
    estimated = (
        (len(request.prompt.encode()) + len(request.system.encode()) + 256)
        * max(provider.input_per_million, provider.long_input_per_million)
        + provider.max_output_tokens
        * max(provider.output_per_million, provider.long_output_per_million)
    ) / 1_000_000
    if estimated > maximum_usd:
        raise ValueError(
            f"This bounded proposal needs a reservation of ${estimated:.2f} at the configured rates; raise the preparation limit or choose a lower-cost model."
        )
    record = {
        "id": request.run_id,
        "status": "prepared",
        "source_dir": inspection["source_dir"],
        "objective": objective,
        "model": provider.model,
        "maximum_usd": maximum_usd,
        "reserved_usd": estimated,
        "usage": None,
        "proposal": None,
        "error": "",
        "inspection": inspection,
        "request": request.model_dump(mode="json"),
        "provider": provider.model_dump(mode="json"),
        "catalog_sha256": catalog.digest,
    }
    _table(store)
    with store.connect() as db:
        db.execute(
            "INSERT INTO setup_proposals VALUES(?,?,?)",
            (record["id"], record["status"], json.dumps(record)),
        )
    return public_proposal(record)


def generate_proposal(store: Store, proposal_id: str) -> dict[str, Any]:
    record = get_proposal(store, proposal_id)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        claimed = db.execute(
            "UPDATE setup_proposals SET status='running' WHERE id=? AND status='prepared'",
            (proposal_id,),
        ).rowcount
    if not claimed:
        raise ValueError(
            "This preparation was already submitted. Inspect its saved result; an interrupted request is never automatically repeated."
        )
    record["status"] = "running"
    _save(store, record)
    from .contracts import ProviderConfig

    usage = Usage(cost_usd=record["reserved_usd"], estimated=True)
    try:
        response = CompatibleProvider(ProviderConfig.model_validate(record["provider"])).complete(
            AgentRequest.model_validate(record["request"])
        )
        usage = response.usage
        record["raw_response"] = response.model_dump(mode="json")
        proposal = Proposal.model_validate(AgentOutput.model_validate(response.data).structured)
        admitted = {item["path"] for item in record["inspection"]["documents"]}
        for suggestion in proposal.suggestions:
            if not set(suggestion.evidence) <= admitted:
                raise ValueError("AI proposal cited files absent from its inspected excerpts.")
        if usage.cost_usd > record["maximum_usd"]:
            raise ValueError(
                "Reported preparation cost exceeded its limit; usage was retained. Check provider pricing before another request."
            )
        record["proposal"] = proposal.model_dump(mode="json")
        record["status"] = "complete"
    except ProviderError as exc:
        usage = exc.usage
        record["error"] = str(exc)
        record["status"] = "failed"
    except Exception:
        record["error"] = (
            "The setup proposal was invalid or interrupted. Its attempt and available usage are retained; no settings were applied."
        )
        record["status"] = "failed"
    finally:
        record["usage"] = usage.model_dump(mode="json")
        _save(store, record)
    return public_proposal(record)


def apply_proposal(
    store: Store, proposal_id: str, config: ResearchConfig, selected: list[int]
) -> ResearchConfig:
    record = get_proposal(store, proposal_id)
    if record["status"] != "complete":
        raise ValueError("Only a completed proposal can be reviewed and applied.")
    if str(Path(config.project.source_dir).expanduser().resolve()) != record["source_dir"]:
        raise ValueError(
            "Project folder changed; inspect the new project before applying suggestions."
        )
    proposal = Proposal.model_validate(record["proposal"])
    if len(set(selected)) != len(selected) or any(
        type(index) is not int or index < 0 or index >= len(proposal.suggestions)
        for index in selected
    ):
        raise ValueError("Choose valid proposal suggestions.")
    evidence = {name for index in selected for name in proposal.suggestions[index].evidence}
    for document in record["inspection"]["documents"]:
        if document["path"] not in evidence:
            continue
        current = read_project_excerpt(
            Path(record["source_dir"]), document["path"], document["read_limit"]
        )
        if current is None or hashlib.sha256(current.encode()).hexdigest() != document["sha256"]:
            raise ValueError(
                "Project evidence changed after inspection. Prepare a new proposal before applying these suggestions."
            )
    data = config.model_dump(mode="json")
    for index in selected:
        suggestion = proposal.suggestions[index]
        set_value(data, suggestion.field, suggestion.value)
    return validate_settings(data)
