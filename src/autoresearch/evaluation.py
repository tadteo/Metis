"""Real-public-data evaluation battery, with explicit capability denominators.

Small public datasets exercise the complete pipeline affordably. They are not a
reproduction of ScientistTwo's 107 frontier-research tasks or evidence of parity.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import shutil
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ResearchConfig
from .contracts import ExecutionConfig, ExperimentResult, ExperimentSpec, RunState
from .engine import Engine
from .execution import Executor
from .privacy import redact
from .runtime_support import content_digest, program_source, write_file
from .store import Store

TASKS: dict[str, dict[str, Any]] = {
    "digits": {
        "title": "Small-data handwritten digit recognition",
        "loader": "load_digits",
        "kind": "classification",
        "metric": "accuracy",
        "source": "https://scikit-learn.org/1.7/modules/generated/sklearn.datasets.load_digits.html",
        "original_source": "https://archive.ics.uci.edu/dataset/80/optical+recognition+of+handwritten+digits",
        "objective": "Investigate an interpretable modification to a standardized nearest-centroid classifier on handwritten digits. Establish the mechanism through component ablations and fixed-protocol evaluation. Compare with credible classical baselines; do not claim new literature novelty from a benchmark gain alone.",
    },
    "diabetes": {
        "title": "Regularized regression on diabetes progression data",
        "loader": "load_diabetes",
        "kind": "regression",
        "metric": "r2",
        "source": "https://scikit-learn.org/1.7/modules/generated/sklearn.datasets.load_diabetes.html",
        "original_source": "https://hastie.su.domains/Papers/LARS/",
        "objective": "Study an interpretable regression method against standardized ridge regression on the public diabetes progression dataset. Preserve the fixed train/test protocol, distinguish predictive experiments from clinical inference, compare established baselines and ablate the proposed mechanism. A small-data improvement does not by itself establish scientific novelty.",
    },
}

_MODEL = program_source("evaluation_model")

_TRAIN = program_source("evaluation_train")

_EVALUATE = program_source("evaluation_scorer")

_PROTECTED = [
    "evaluate.py",
    "protocol.json",
    "train_data.json",
    "test_features.json",
    "test_targets.json",
]


def _read_suite(destination: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads((destination / "suite.json").read_text())
    if value.get("schema_version") != 1:
        raise ValueError("unsupported evaluation suite schema")
    return value


def _save_suite(destination: Path, value: dict[str, Any]) -> None:
    write_file(destination, "suite.json", json.dumps(value, indent=2, allow_nan=False))


def prepare_suite(destination: Path, base_config: ResearchConfig | None = None) -> dict[str, Any]:
    """Materialize deterministic public datasets and runnable protected task configs."""
    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(
            "evaluation destination must be empty; existing attempts are never overwritten"
        )
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        datasets = importlib.import_module("sklearn.datasets")
        selection = importlib.import_module("sklearn.model_selection")
        sklearn = importlib.import_module("sklearn")
    except ImportError:
        raise ValueError("Install the pinned evaluation extra to prepare public datasets") from None
    base = (base_config or ResearchConfig()).model_copy(deep=True)
    base.mode = "live"
    suite: dict[str, Any] = {
        "schema_version": 1,
        "created_at": time.time(),
        "split_seed": 20260929,
        "purpose": "real-data pipeline and research-method evaluation; not original ScientistTwo benchmark parity",
        "dataset_package": {"scikit-learn": sklearn.__version__},
        "tasks": [],
        "runs": [],
        "baseline_attempts": [],
        "quality_ratings": [],
        "capability_claim": "unmeasured",
    }
    for identifier, task in TASKS.items():
        data = getattr(datasets, task["loader"])()
        indices = list(range(len(data.target)))
        train_indices, test_indices = selection.train_test_split(
            indices,
            test_size=0.25,
            random_state=suite["split_seed"],
            stratify=data.target if task["kind"] == "classification" else None,
        )
        train_x = data.data[train_indices].tolist()
        train_y = data.target[train_indices].tolist()
        subset, _ = selection.train_test_split(
            list(range(len(train_y))),
            train_size=0.3,
            random_state=suite["split_seed"] + 1,
            stratify=train_y if task["kind"] == "classification" else None,
        )
        protocol = {
            "kind": task["kind"],
            "metric": task["metric"],
            "subset_indices": subset,
            "class_labels": sorted(set(train_y)) if task["kind"] == "classification" else [],
            "train_indices": train_indices,
            "test_indices": test_indices,
            "split_seed": suite["split_seed"],
        }
        source = destination / identifier / "source"
        source.mkdir(parents=True, mode=0o700)
        contents = {
            "model.py": _MODEL,
            "train.py": _TRAIN,
            "evaluate.py": _EVALUATE,
            "protocol.json": json.dumps(protocol),
            "train_data.json": json.dumps({"x": train_x, "y": train_y}),
            "test_features.json": json.dumps(data.data[test_indices].tolist()),
            "test_targets.json": json.dumps(data.target[test_indices].tolist()),
        }
        for filename, content in contents.items():
            write_file(source, filename, content)
        config = base.model_copy(deep=True)
        config.project.source_dir = str(source)
        config.project.include = ["*"]
        config.project.baseline_argv = ["python3", "train.py", "--split", "subset"]
        config.project.evaluator_argv = ["python3", "evaluate.py"]
        config.project.protected_paths = list(_PROTECTED)
        config.project.seeds = [0, 1, 2]
        config.project.metrics = {"score": "max"}
        config.project.primary_metric = "score"
        config.project.sota = {}
        config.project.baseline_expected = {}
        config.project.reproduction_tolerance = 1e-8
        config.project.dataset_manifest = {
            "dataset": identifier,
            "source": task["original_source"],
            "protocol_sha256": content_digest(protocol),
            "data_sha256": content_digest({"x": data.data.tolist(), "y": data.target.tolist()}),
        }
        config.project.dataset_manifest.update(
            {
                f"sha256:{name}": hashlib.sha256(contents[name].encode()).hexdigest()
                for name in _PROTECTED
            }
        )
        config.project.specification = (
            f"Evaluation battery task {identifier}; score is {task['metric']}. "
            "Reference full metrics are measured registered baselines, not claimed published SOTA. "
            "Train on train_data.json only, using protocol.json subset_indices during subset stages and all training rows in full stages. "
            "Never access test_targets.json during fitting or select methods by held-out labels. "
            "Never retrieve alternate dataset copies or change splits, targets, evaluator or protocol. "
            "Standardization and all learned preprocessing must be fit on training rows only. "
            "Full, ablation and rebuttal commands must use --split full. Record each mechanism and component removal. "
            "Repeated seeds provide reproducibility observations, not an automatic significance test. "
            "These public labels are not cryptographically hidden; independent code/protocol audit is required."
        )
        config_path = destination / identifier / "config.json"
        write_file(destination, f"{identifier}/config.json", config.model_dump_json(indent=2))
        suite["tasks"].append(
            {
                "id": identifier,
                **task,
                "config": str(config_path.relative_to(destination)),
                "source": str(source.relative_to(destination)),
                "protocol_sha256": content_digest(protocol),
                "samples": len(indices),
                "train_samples": len(train_indices),
                "test_samples": len(test_indices),
                "subset_samples": len(subset),
                "baseline_ready": False,
            }
        )
    _save_suite(destination, suite)
    return suite


def baseline_suite(destination: Path, execution: ExecutionConfig | None = None) -> dict[str, Any]:
    """Execute every registered baseline seed; preserve failures and durable receipts."""
    destination = destination.resolve()
    suite = _read_suite(destination)
    for task in suite["tasks"]:
        config = ResearchConfig.model_validate_json((destination / task["config"]).read_text())
        settings = execution or config.execution
        executor = Executor(settings)
        results: dict[str, list[ExperimentResult]] = {"subset": [], "full": []}
        for split in results:
            for seed in config.project.seeds:
                identifier = f"{task['id']}-{split}-{seed}"
                receipt_name = f"baseline/{identifier}.json"
                receipt = destination / receipt_name
                workspace = destination / "baseline" / identifier
                spec = ExperimentSpec(
                    id=identifier,
                    kind=f"evaluation_{split}",
                    workspace=str(workspace),
                    argv=["python3", "train.py", "--split", split],
                    seed=seed,
                    timeout_seconds=config.project.experiment_timeout,
                    metadata={
                        "evaluator_argv": config.project.evaluator_argv,
                        "protected_files": _PROTECTED,
                        "dataset_manifest": config.project.dataset_manifest,
                    },
                )
                existing = next(
                    (a for a in suite["baseline_attempts"] if a["id"] == identifier), None
                )
                if receipt.exists():
                    result = ExperimentResult.model_validate_json(receipt.read_text())
                    if result.status == "pending" and result.job_id:
                        result = executor.poll(spec, result.job_id)
                        write_file(destination, receipt_name, result.model_dump_json(indent=2))
                elif existing:
                    # Do not silently replay a crashed expensive baseline.
                    result = ExperimentResult(
                        id=identifier,
                        status="failed",
                        stderr="Baseline execution was interrupted without a durable receipt; reconcile before a new registered attempt.",
                    )
                    write_file(destination, receipt_name, result.model_dump_json(indent=2))
                else:
                    workspace.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    shutil.copytree(destination / task["source"], workspace)
                    suite["baseline_attempts"].append(
                        {
                            "id": identifier,
                            "task": task["id"],
                            "split": split,
                            "seed": seed,
                            "started_at": time.time(),
                            "receipt": receipt_name,
                        }
                    )
                    _save_suite(destination, suite)
                    try:
                        result = executor.run(spec)
                    except (ValueError, OSError) as error:
                        result = ExperimentResult(id=identifier, status="failed", stderr=str(error))
                    write_file(destination, receipt_name, result.model_dump_json(indent=2))
                results[split].append(result)
        valid = all(
            r.status == "completed" and "score" in r.metrics
            for rows in results.values()
            for r in rows
        )
        task["baseline_ready"] = valid
        task["baseline_summary"] = {
            split: {
                "attempted": len(rows),
                "completed": sum(r.status == "completed" for r in rows),
                "scores": [r.metrics["score"] for r in rows if r.status == "completed"],
                "seconds": sum(r.duration_seconds for r in rows),
            }
            for split, rows in results.items()
        }
        if valid:
            config.project.baseline_expected = {
                "score": statistics.mean(r.metrics["score"] for r in results["subset"])
            }
            config.project.sota = {
                "score": statistics.mean(r.metrics["score"] for r in results["full"])
            }
            write_file(destination, task["config"], config.model_dump_json(indent=2))
        _save_suite(destination, suite)
    return {
        "registered_tasks": len(suite["tasks"]),
        "ready_tasks": sum(t["baseline_ready"] for t in suite["tasks"]),
        "baseline_attempted": len(suite["baseline_attempts"]),
        "tasks": [{"id": t["id"], **t["baseline_summary"]} for t in suite["tasks"]],
        "scientific_capability": "not evaluated by baseline execution",
    }


def variants(
    base_config: ResearchConfig, reference_config: ResearchConfig | None = None
) -> dict[str, Any]:
    """Executable paired-ablation configs; never invent an upstream model endpoint."""
    configurations: dict[str, ResearchConfig] = {"configured": base_config.model_copy(deep=True)}
    two = base_config.model_copy(deep=True)
    two.pipeline.novelty_references = 2
    two.pipeline.novelty_queries = 1
    two.literature.max_results = 2
    two.literature.results_per_provider = 2
    two.literature.min_novelty_sources = 2
    configurations["two-references"] = two
    single = base_config.model_copy(deep=True)
    single.pipeline.critics = 1
    single.role_panels = {}
    configurations["single-critic"] = single
    no_escalation = base_config.model_copy(deep=True)
    no_escalation.frontier_provider = None
    configurations["no-escalation"] = no_escalation
    pareto = base_config.model_copy(deep=True)
    pareto.project.result_preference = "pareto"
    configurations["pareto-preference"] = pareto
    scientific = base_config.model_copy(deep=True)
    scientific.project.result_preference = "scientific_critic"
    configurations["scientific-preference"] = scientific
    if base_config.laya.enabled:
        laya_enabled = base_config.model_copy(deep=True)
        configurations["laya-enabled"] = laya_enabled
        laya_disabled = base_config.model_copy(deep=True)
        laya_disabled.laya.enabled = False
        configurations["laya-disabled"] = laya_disabled
    if reference_config is not None:
        reference = base_config.model_copy(deep=True)
        reference.provider = reference_config.provider
        reference.cheap_provider = reference_config.cheap_provider
        reference.frontier_provider = reference_config.frontier_provider
        reference.role_providers = reference_config.role_providers
        reference.role_panels = reference_config.role_panels
        reference.role_commands = reference_config.role_commands
        reference.role_command_max_cost_usd = reference_config.role_command_max_cost_usd
        configurations["published-routing"] = reference
    return {
        "configs": {name: cfg.model_dump(mode="json") for name, cfg in configurations.items()},
        "requires_operator_reference": {
            "published-routing": "Supply a verified config for the paper's actual models and coding harness; no guessed endpoint or model label counts as a reproduction."
        }
        if reference_config is None
        else {},
        "paired_protocol": "Same tasks, initial inputs, data hashes, scientific budgets and seeds; report all task attempts. Compare dimensions separately. No parity claim follows from an unexecuted variant.",
    }


def run_suite(
    store: Store,
    destination: Path,
    max_steps: int | None = None,
    variant: str = "configured",
    reference_config: ResearchConfig | None = None,
) -> dict[str, Any]:
    """Create or resume each registered live task, retaining blocked and failed runs."""
    destination = destination.resolve()
    suite = _read_suite(destination)
    for task in suite["tasks"]:
        if not task["baseline_ready"]:
            raise ValueError("Run registered baselines successfully before autonomous evaluation")
        config = ResearchConfig.model_validate_json((destination / task["config"]).read_text())
        available = variants(config, reference_config)["configs"]
        if variant not in available:
            raise ValueError("Unknown or unavailable evaluation variant")
        config = ResearchConfig.model_validate(available[variant])
        entry = next(
            (r for r in suite["runs"] if r["task"] == task["id"] and r["variant"] == variant), None
        )
        engine = Engine(store, config)
        if entry is None:
            # Register the attempted denominator before creating a run or calling an API.
            entry = {
                "task": task["id"],
                "variant": variant,
                "run_id": None,
                "started_at": time.time(),
                "error": "",
                "config_sha256": content_digest(config.model_dump(mode="json")),
            }
            suite["runs"].append(entry)
            _save_suite(destination, suite)
            try:
                state = engine.create(task["title"], task["objective"])
                entry["run_id"] = state.id
                _save_suite(destination, suite)
            except (ValueError, OSError) as error:
                entry["error"] = str(redact(str(error)))
                _save_suite(destination, suite)
                continue
        if entry["run_id"]:
            try:
                engine.run(entry["run_id"], max_steps=max_steps)
            except Exception as error:
                # Failure is an evaluation outcome, retained instead of deleting the task.
                entry["error"] = str(redact(str(error)))
            _save_suite(destination, suite)
    return report_suite(store, destination)


def _events(store: Store, run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = 0
    while rows := store.events(run_id, after=cursor):
        events.extend(rows)
        cursor = rows[-1]["seq"]
    return events


def _duration(state: RunState) -> float | None:
    try:
        return max(
            0.0,
            (
                datetime.fromisoformat(state.updated_at) - datetime.fromisoformat(state.created_at)
            ).total_seconds(),
        )
    except ValueError:
        return None


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def report_suite(store: Store, destination: Path) -> dict[str, Any]:
    """Separate process measures, independent quality labels, costs and failures."""
    suite = _read_suite(destination)
    reports: list[dict[str, Any]] = []
    for entry in suite["runs"]:
        row: dict[str, Any] = dict(entry)
        if not entry["run_id"]:
            row.update(status="failed_creation", dimensions={})
            reports.append(row)
            continue
        state = store.get_run(entry["run_id"])
        events = _events(store, state.id)
        coded = [
            e["payload"]
            for e in events
            if e["kind"] == "coding_step"
            and isinstance(e["payload"].get("action"), dict)
            and e["payload"].get("action", {}).get("tool") == "command"
        ]
        sessions = [
            json.loads(path.read_text())
            for path in (store.run_dir(state.id) / "coding").glob("*/checkpoint.json")
        ]
        completed = [e for e in state.experiments if e.status == "completed"]
        ablations = [e for e in state.experiments if e.provenance.get("kind") == "ablation"]
        attempted_ids = {e.provenance.get("idea_id") for e in state.experiments}
        if state.pending_experiment:
            attempted_ids.add(state.pending_experiment.metadata.get("idea_id"))
        attempted_ideas = [i for i in state.ideas if i.id in attempted_ids]
        success_ideas = [i for i in attempted_ideas if i.status in {"good", "superseded"}]
        ratings = [
            r
            for r in suite["quality_ratings"]
            if r.get("task") == entry["task"] and r.get("variant") == entry["variant"]
        ]
        quality: dict[str, Any] = {}
        for name in ("idea_novelty", "ablation_quality", "paper_writing", "reviewer_quality"):
            labels = [
                r
                for r in ratings
                if r.get("dimension") == name
                and r.get("independent") is True
                and r.get("evidence_artifacts")
                and r.get("rater_id")
                and isinstance(r.get("score"), (float, int))
                and not isinstance(r.get("score"), bool)
                and math.isfinite(r["score"])
                and 0 <= r["score"] <= 1
            ]
            quality[name] = {
                "score": statistics.mean(r["score"] for r in labels) if labels else None,
                "independent_raters": len({r.get("rater_id") for r in labels}),
                "labels": labels,
                "status": "measured" if labels else "unmeasured: independent adjudication required",
            }
        literature = {
            "retrieved_sources": len(state.evidence),
            "inspectable_sources": sum(bool(e.abstract or e.full_text) for e in state.evidence),
            "full_text_sources": sum(bool(e.full_text) for e in state.evidence),
            "search_failures": None,
            "search_failure_status": "inspect retained provider reports; absence of a failure event is not zero failures",
            "recall": None,
            "recall_status": "requires independent task-specific relevant-paper set",
        }
        integrity_events = [
            e for e in events if "integrity" in e["kind"] or e["kind"] == "claim_audit"
        ]
        violations = [
            e
            for e in integrity_events
            if e["payload"].get("passed") is False or e["payload"].get("decision") == "reject"
        ]
        usage = store.usage(state.id)
        dimensions = {
            "idea_novelty_quality": quality["idea_novelty"],
            "baseline_reproduction": {
                "passed": bool(state.baseline),
                "measured_metrics": state.baseline,
            },
            "coding_success": _rate(sum(bool(s.get("completed")) for s in sessions), len(sessions)),
            "coding_command_success": _rate(
                sum(
                    c.get("observation", {}).get("result", {}).get("status") == "completed"
                    for c in coded
                ),
                len(coded),
            ),
            "experiment_correctness": {
                **_rate(
                    len(completed),
                    len(state.experiments) + int(state.pending_experiment is not None),
                ),
                "meaning": "execution with valid metrics; scientific correctness requires independent integrity audit",
            },
            "improvement_rate": _rate(len(success_ideas), len(attempted_ideas)),
            "ablation_execution": _rate(
                sum(e.status == "completed" for e in ablations), len(ablations)
            ),
            "ablation_quality": quality["ablation_quality"],
            "literature_coverage": literature,
            "paper_writing_quality": quality["paper_writing"],
            "reviewer_quality": quality["reviewer_quality"],
            "integrity_failures": {
                "detected": len(violations),
                "audits_observed": len(integrity_events),
                "audit_complete": state.stage.value == "complete" and state.status == "completed",
            },
            "cost": {
                **usage,
                "compute_cost_usd": None,
                "compute_cost_status": "operator billing import required",
            },
            "runtime": {
                "wall_seconds": _duration(state),
                "experiment_seconds": sum(e.duration_seconds for e in state.experiments),
                "coding_seconds": sum(
                    c.get("observation", {}).get("result", {}).get("duration_seconds", 0)
                    for c in coded
                ),
            },
        }
        row.update(
            status=state.status,
            outcome=state.outcome,
            error=entry["error"] or state.error,
            dimensions=dimensions,
            experiments_attempted=len(state.experiments)
            + int(state.pending_experiment is not None),
            experiments_failed=sum(
                e.status in {"failed", "timeout", "cancelled"} for e in state.experiments
            ),
            ideas_proposed=len(state.ideas),
        )
        reports.append(row)
    report = {
        "schema_version": 1,
        "registered_tasks": len(suite["tasks"]),
        "attempted_task_variants": len(reports),
        "completed_task_variants": sum(r["status"] == "completed" for r in reports),
        "failed_or_blocked_task_variants": sum(
            r["status"] in {"failed", "blocked", "failed_creation", "budget_exhausted", "stopped"}
            for r in reports
        ),
        "runs": reports,
        "capability_parity": "unmeasured",
        "scope": suite["purpose"],
        "statistical_significance": "not inferred from repeated seeds or aggregate gains",
    }
    write_file(destination, "report.json", json.dumps(redact(report), indent=2, allow_nan=False))
    return report
