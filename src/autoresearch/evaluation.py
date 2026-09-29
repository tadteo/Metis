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

from .catalog import load_catalog
from .config import ProjectConfig, ResearchConfig
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
        "loader_kwargs": {"scaled": False},
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
    spec_dir = base.specification_dir
    catalog = load_catalog(Path(spec_dir) if spec_dir else None)
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
        data = getattr(datasets, task["loader"])(**task.get("loader_kwargs", {}))
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
        config.project = ProjectConfig.model_validate(
            {
                **config.project.model_dump(mode="json"),
                "source_dir": str(source),
                "include": ["*"],
                "baseline_argv": ["python3", "train.py", "--split", "subset"],
                "evaluator_argv": ["python3", "evaluate.py"],
                "protected_paths": list(_PROTECTED),
                "seeds": [0, 1, 2],
                "metrics": {"score": "max"},
                "metric_units": {
                    "score": "fraction" if task["kind"] == "classification" else "scalar"
                },
                "analysis_artifacts": [],
                "primary_metric": "score",
                "sota": {},
                "baseline_expected": {},
                "reproduction_tolerance": 1e-8,
            }
        )
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
        config.project.specification = catalog.render_task(
            "evaluation", identifier=identifier, metric=task["metric"]
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
                        "metric_units": config.project.metric_units,
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
                        workspace.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        shutil.copytree(destination / task["source"], workspace)
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
                entry.setdefault("execution_errors", []).append(
                    {
                        "observed_at": time.time(),
                        "error": entry["error"],
                        "type": type(error).__name__,
                    }
                )
            else:
                entry["error"] = ""
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


def _audit_result(kind: str, payload: dict[str, Any], source: str) -> dict[str, Any]:
    """One adjudicated audit, rather than every individual reviewer/model call."""
    raw_decision = payload.get("decision")
    decision = raw_decision if isinstance(raw_decision, str) else None
    issues = payload.get("issues", [])
    outcome = "unverified"
    if payload.get("passed") is False or payload.get("verified") is False or issues:
        outcome = "failed"
    elif decision in {"refine", "reject"}:
        outcome = "failed"
    elif payload.get("passed") is True or decision == "accept":
        outcome = "passed"
    elif kind == "reference_audit" and isinstance(payload.get("issues"), list):
        outcome = "passed"
    return {
        "kind": kind,
        "experiment_id": payload.get("id", payload.get("experiment_id")),
        "decision": decision if decision in {"accept", "refine", "reject"} else None,
        "outcome": outcome,
        "issues": sorted(str(item) for item in issues)
        if isinstance(issues, list)
        else [str(issues)],
        "sources": [source],
    }


def _merge_audit_mirrors(
    primary: list[dict[str, Any]], secondary: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pair event/memory copies one-to-one; repeated identical attempts stay distinct."""
    result = [{**item, "sources": list(item["sources"])} for item in primary]
    available: dict[str, list[int]] = {}
    for index, item in enumerate(primary):
        key = content_digest({k: v for k, v in item.items() if k != "sources"})
        available.setdefault(key, []).append(index)
    for item in secondary:
        key = content_digest({k: v for k, v in item.items() if k != "sources"})
        matches = available.get(key, [])
        if matches:
            result[matches.pop(0)]["sources"].extend(item["sources"])
        else:
            result.append(item)
    return result


def _integrity_summary(state: RunState, events: list[dict[str, Any]]) -> dict[str, Any]:
    event_audits: list[dict[str, Any]] = []
    memory_audits: list[dict[str, Any]] = []
    final_individual: list[dict[str, Any]] = []
    final_panel_members: list[dict[str, Any]] = []
    seen_events: set[Any] = set()
    seen_memory: set[tuple[str, Any]] = set()
    for index, event in enumerate(events):
        event_id = event.get("seq", index)
        if event_id in seen_events:
            continue
        seen_events.add(event_id)
        kind, payload = event["kind"], event["payload"]
        source = f"event:{event_id}"
        if kind in {"experiment_integrity", "claim_audit", "reference_audit"}:
            event_audits.append(_audit_result(kind, payload, source))
        elif kind == "integrity" or (
            kind in {"integrity_panel", "agent_consensus"} and payload.get("role") == "integrity"
        ):
            event_audits.append(_audit_result("final_integrity", payload, source))
            outputs = payload.get("outputs", payload.get("individual_outputs", []))
            if isinstance(outputs, list):
                for reviewer, output in enumerate(outputs):
                    if isinstance(output, dict):
                        final_panel_members.append(
                            _audit_result(
                                "final_integrity_individual",
                                output,
                                f"{source}:reviewer:{reviewer}",
                            )
                        )
        elif kind == "agent_completed" and payload.get("role") == "integrity":
            output = payload.get("output")
            if isinstance(output, dict):
                final_individual.append(_audit_result("final_integrity_individual", output, source))
    for index, item in enumerate(state.memory):
        kind = item.get("kind")
        if kind == "critique" and item.get("stage") == "integrity":
            kind = "final_integrity"
        if kind not in {"claim_audit", "reference_audit", "final_integrity"}:
            continue
        # A version identifies a checkpointed adjudication. Old unversioned
        # histories retain separate occurrences rather than inventing identities.
        identity = (str(kind), item.get("version", f"unversioned-{index}"))
        if identity in seen_memory:
            continue
        seen_memory.add(identity)
        memory_audits.append(_audit_result(str(kind), item, f"memory:{index}"))
    audits = _merge_audit_mirrors(event_audits, memory_audits)
    final_individual = _merge_audit_mirrors(final_panel_members, final_individual)
    # Individual outputs may exist before a crash prevents a final consensus.
    # Expose their failures separately; never label them a completed final audit.
    by_kind: dict[str, dict[str, int]] = {}
    for audit in audits:
        counts = by_kind.setdefault(audit["kind"], {"observed": 0, "failed": 0, "unverified": 0})
        counts["observed"] += 1
        counts["failed"] += audit["outcome"] == "failed"
        counts["unverified"] += audit["outcome"] == "unverified"
    return {
        "detected": sum(a["outcome"] == "failed" for a in audits),
        "audits_observed": len(audits),
        "audits_unverified": sum(a["outcome"] == "unverified" for a in audits),
        "by_kind": by_kind,
        "audits": audits,
        "individual_final_reviews_observed": len(final_individual),
        "individual_final_review_failures": sum(a["outcome"] == "failed" for a in final_individual),
        "individual_final_reviews_unverified": sum(
            a["outcome"] == "unverified" for a in final_individual
        ),
        "audit_complete": state.stage.value == "complete" and state.status == "completed",
        "counting_unit": "Adjudicated audit attempts; mirrored events/memory count once, individual reviewers are separate",
    }


def _literature_summary(
    store: Store, state: RunState, events: list[dict[str, Any]]
) -> dict[str, Any]:
    reports: dict[str, dict[str, Any]] = {}
    unidentified_report_signatures: set[str] = set()
    unreadable_artifacts: list[str] = []

    def register(report: Any) -> None:
        if not isinstance(report, dict) or not isinstance(report.get("providers"), list):
            return
        if not report.get("retrieved_at") or not report.get("query"):
            unidentified_report_signatures.add(content_digest(report))
            return
        # The same cumulative search_history appears in multiple idea artifacts.
        # Query + timestamp preserve genuine repeated calls while deduplicating copies.
        identity = content_digest(
            {
                key: report.get(key)
                for key in ("query", "retrieved_at", "cutoff", "limit", "results_per_provider")
            }
        )
        reports[identity] = report

    for artifact in store.artifacts(state.id):
        if artifact["kind"] != "novelty_search":
            continue
        try:
            raw = store.artifact_content(state.id, artifact["id"])
            value = json.loads(raw)
            for report in value.get("reports", []):
                register(report)
        except (OSError, ValueError, AttributeError, TypeError):
            unreadable_artifacts.append(artifact["id"])
    failure_signatures: set[str] = set()
    coverage_count = 0
    for event in events:
        if event["kind"] in {"literature_search", "literature_search_report"}:
            register(event["payload"].get("report", event["payload"]))
        if event["kind"] == "literature_coverage":
            coverage_count += 1
            for failure in event["payload"].get("coverage", {}).get("provider_failures", []):
                failure_signatures.add(content_digest(failure))
    # Legacy snapshots keep failure evidence even when query-level logs are absent.
    for item in state.memory:
        if item.get("kind") == "novelty_search":
            for failure in item.get("coverage", {}).get("provider_failures", []):
                failure_signatures.add(content_digest(failure))
    attempts = [
        provider
        for report in reports.values()
        for provider in report["providers"]
        if isinstance(provider, dict)
    ]
    statuses = [p.get("status") if isinstance(p.get("status"), str) else None for p in attempts]
    for provider, status in zip(attempts, statuses, strict=True):
        if status in {"failed", "error", "timeout", "cancelled"}:
            failure_signatures.add(content_digest(provider))
    failures = sum(status in {"failed", "error", "timeout", "cancelled"} for status in statuses)
    unknown = sum(
        status not in {"completed", "failed", "error", "timeout", "cancelled"}
        for status in statuses
    )
    measured = bool(reports)
    return {
        "retrieved_sources": len(state.evidence),
        "inspectable_sources": sum(bool(e.abstract or e.full_text) for e in state.evidence),
        "full_text_sources": sum(bool(e.full_text) for e in state.evidence),
        "search_failures": failures if measured else None,
        "provider_attempts_observed": len(attempts) if measured else None,
        "provider_outcomes_unknown": unknown if measured else None,
        "search_requests_observed": len(reports) if measured else None,
        "cached_search_requests": sum(bool(r.get("cached")) for r in reports.values())
        if measured
        else None,
        "coverage_events_observed": coverage_count,
        "distinct_failure_signatures": len(failure_signatures),
        "unidentified_report_signatures": len(unidentified_report_signatures),
        "unreadable_search_artifacts": unreadable_artifacts,
        "search_failure_status": "Measured only over timestamped retained novelty/provider reports; other searches are not certified"
        if measured
        else "Unmeasured: cumulative coverage snapshots alone do not identify individual provider attempts",
        "recall": None,
        "recall_status": "requires independent task-specific relevant-paper set",
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
        observed_experiments = {experiment.id for experiment in state.experiments}
        # Refinements receive their own hypothesis ID after execution. Their
        # archived links retain that attempted idea even when it is rejected.
        for item in state.memory:
            hypothesis = item.get("hypothesis")
            links = item.get("experiment_ids")
            if (
                item.get("kind") in {"refinement_proposed", "candidate_decision"}
                and isinstance(hypothesis, dict)
                and isinstance(hypothesis.get("id"), str)
                and isinstance(links, list)
                and any(
                    isinstance(identifier, str) and identifier in observed_experiments
                    for identifier in links
                )
            ):
                attempted_ids.add(hypothesis["id"])
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
        literature = _literature_summary(store, state, events)
        usage = store.usage(state.id)
        dimensions = {
            "idea_novelty_quality": quality["idea_novelty"],
            "baseline_reproduction": {
                "passed": bool(state.baseline),
                "measured_metrics": state.baseline,
            },
            "coding_success": _rate(sum(bool(s.get("completed")) for s in sessions), len(sessions)),
            "coding_command_success": {
                **_rate(
                    sum(
                        c.get("observation", {}).get("result", {}).get("status") == "completed"
                        for c in coded
                    ),
                    len(coded),
                ),
                "meaning": "Completed command observations only; interrupted commands remain in session receipts",
            },
            "experiment_correctness": {
                **_rate(
                    len(completed),
                    len(state.experiments) + int(state.pending_experiment is not None),
                ),
                "meaning": "execution with valid metrics; scientific correctness requires independent integrity audit",
            },
            "improvement_rate": {
                **_rate(len(success_ideas), len(attempted_ideas)),
                "meaning": "Validated full-benchmark successes over all attempted ideas, including subset failures",
            },
            "ablation_execution": _rate(
                sum(e.status == "completed" for e in ablations),
                len(ablations)
                + int(
                    bool(state.pending_experiment and state.pending_experiment.kind == "ablation")
                ),
            ),
            "ablation_quality": quality["ablation_quality"],
            "literature_coverage": literature,
            "paper_writing_quality": quality["paper_writing"],
            "reviewer_quality": quality["reviewer_quality"],
            "integrity_failures": _integrity_summary(state, events),
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
            status="failed_execution" if entry["error"] else state.status,
            run_status=state.status,
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
            r["status"]
            in {
                "failed",
                "blocked",
                "failed_creation",
                "failed_execution",
                "budget_exhausted",
                "stopped",
            }
            for r in reports
        ),
        "runs": reports,
        "capability_parity": "unmeasured",
        "scope": suite["purpose"],
        "statistical_significance": "not inferred from repeated seeds or aggregate gains",
    }
    write_file(destination, "report.json", json.dumps(redact(report), indent=2, allow_nan=False))
    return report
