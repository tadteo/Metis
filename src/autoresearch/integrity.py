"""Claim evidence checks; execution receipts, not model annotations, establish support."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from .contracts import ExperimentResult, Model, RunState

MetricUnit = Literal[
    "scalar", "fraction", "percent", "percentage_points", "seconds", "milliseconds"
]
# Numeric literals are deliberately bounded to a documented, unambiguous notation.
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_COMPARATOR = r"<=|>=|<|>|=|\\leq|\\geq|\\le|\\ge"
_LITERAL = re.compile(
    rf"(?P<comparator>{_COMPARATOR})?\s*(?P<number>{_NUMBER})\s*(?P<unit>\\%|%|percent|percentage points|milliseconds|seconds|ms|s)?"
)
_TOKEN = re.compile(
    rf"(?<![\w.])(?:{_COMPARATOR})?\s*{_NUMBER}(?:\s*(?:\\%|%|percent\b|percentage points\b|milliseconds\b|seconds\b|ms\b|s\b))?(?!\w|\.\d)"
)
_UNITS = {
    "": "scalar",
    "%": "percent",
    "\\%": "percent",
    "percent": "percent",
    "percentage points": "percentage_points",
    "s": "seconds",
    "seconds": "seconds",
    "ms": "milliseconds",
    "milliseconds": "milliseconds",
}


class Claim(Model):
    id: str
    kind: str
    text: str
    experiment_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    code_paths: list[str] = Field(default_factory=list)
    metric: str = ""
    # Literal displayed value, not a silently converted measurement.
    value: float | None = None
    numeric_span: str = ""
    aggregation: str = "individual"
    rounding_tolerance: float | None = Field(default=None, ge=0, le=0.05)
    analysis_experiment_id: str = ""
    analysis_artifact: str = ""
    statistic: str = "p_value"


class StatisticalAnalysis(Model):
    """Declared JSON output of executed analysis; a method name is not semantic proof."""

    schema_version: Literal[1] = 1
    method: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    statistic: Literal[
        "p_value", "test_statistic", "confidence_lower", "confidence_upper", "effect_size"
    ]
    value: float
    input_experiment_ids: list[str] = Field(min_length=1)
    input_fingerprints: dict[str, str]


def analysis_input(result: ExperimentResult) -> dict[str, Any]:
    """Engine-owned input descriptor, including an exact fingerprint of its evidence."""
    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return {
        "id": result.id,
        "metrics": dict(result.metrics),
        "provenance": {
            key: result.provenance[key]
            for key in ("kind", "seed", "idea_id", "selected_idea", "plan")
            if key in result.provenance
        },
        "fingerprint": hashlib.sha256(payload.encode()).hexdigest(),
    }


def _artifact_bytes(root: Path, relative: str) -> bytes:
    # Reject symlinks in every component, absolute paths, and traversal.
    import os
    import stat

    from .execution import _parent

    with _parent(root, relative) as (descriptor, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("analysis artifact must be a regular file")
            data = stream.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("analysis artifact exceeds 1 MB")
    return data


def capture_statistical_analyses(
    result: ExperimentResult, root: Path, paths: list[str], inputs: list[dict[str, Any]]
) -> None:
    """Executor-only capture after successful execution and deletion of stale outputs.

    Persist invalid output diagnostics too; never promote missing/invalid analyses.
    Input records must come from the engine, not the workload or the claim extractor.
    """
    receipts: dict[str, Any] = {}
    known = {item["id"]: item["fingerprint"] for item in inputs}
    measured = {item["id"]: item["metrics"] for item in inputs}
    for relative in paths:
        try:
            data = _artifact_bytes(root, relative)
            analysis = StatisticalAnalysis.model_validate_json(data)
            ids = analysis.input_experiment_ids
            if len(set(ids)) != len(ids) or set(analysis.input_fingerprints) != set(ids):
                raise ValueError("analysis inputs must be unique and exactly fingerprinted")
            if any(known.get(eid) != analysis.input_fingerprints[eid] for eid in ids):
                raise ValueError("analysis inputs do not match the registered execution inputs")
            if any(analysis.metric not in measured[eid] for eid in ids):
                raise ValueError(
                    "analysis metric is missing from its registered input measurements"
                )
            if analysis.statistic == "p_value" and not 0 <= analysis.value <= 1:
                raise ValueError("p-value must be between zero and one")
            receipts[relative] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "analysis": analysis.model_dump(),
                "execution_id": result.id,
            }
        except (OSError, ValueError, ValidationError) as exc:
            receipts[relative] = {"error": str(exc), "execution_id": result.id}
    result.provenance["statistical_analyses"] = receipts


def _literal(claim: Claim) -> tuple[float, str, str, float]:
    candidates = [m.group().strip() for m in _TOKEN.finditer(claim.text)]
    span = claim.numeric_span or (candidates[0] if len(candidates) == 1 else "")
    if not span or span not in candidates or claim.text.count(span) != 1:
        raise ValueError(
            "numeric_span must identify one complete, unique displayed number including its unit/comparator"
        )
    match = _LITERAL.fullmatch(span)
    if not match:
        raise ValueError("unsupported numeric literal")
    number = Decimal(match["number"])
    value = float(number)
    if claim.value is None or value != claim.value:
        raise ValueError("claim value disagrees with its literal manuscript number")
    exponent = number.as_tuple().exponent
    assert isinstance(exponent, int)
    half_unit = float(Decimal(5).scaleb(exponent - 1))
    # A model cannot grant itself a wider tolerance than the manuscript precision.
    if claim.rounding_tolerance is not None and claim.rounding_tolerance > half_unit + 1e-15:
        raise ValueError("rounding tolerance exceeds the displayed precision")
    tolerance = (
        half_unit if claim.rounding_tolerance is None else min(half_unit, claim.rounding_tolerance)
    )
    comparator = match["comparator"] or "="
    comparator = {r"\leq": "<=", r"\le": "<=", r"\geq": ">=", r"\ge": ">="}.get(
        comparator, comparator
    )
    return value, _UNITS[match["unit"] or ""], comparator, tolerance


def _converted(value: float, source: str, target: str) -> float:
    if source == target or target == "scalar":
        # Unadorned numbers retain the registered measurement unit without rescaling.
        return value
    conversions = {
        ("fraction", "percent"): 100.0,
        ("fraction_difference", "percentage_points"): 100.0,
        ("seconds", "milliseconds"): 1000.0,
        ("milliseconds", "seconds"): 0.001,
    }
    if (source, target) not in conversions:
        raise ValueError("displayed unit has no registered metric-unit conversion")
    return value * conversions[(source, target)]


def _compare_literal(
    claim: Claim, expected: float, source_unit: str = "scalar", *, inequalities: bool = False
) -> None:
    value, unit, comparator, rounding = _literal(claim)
    actual = _converted(expected, source_unit, unit)
    if comparator != "=" and not inequalities:
        raise ValueError(
            "numerical result requires equality; statistical bounds use statistical claims"
        )
    matches = {
        "<": actual < value,
        "<=": actual <= value,
        ">": actual > value,
        ">=": actual >= value,
        "=": abs(Decimal(str(actual)) - Decimal(str(value))) <= Decimal(str(rounding)),
    }[comparator]
    if not matches:
        raise ValueError("reported number disagrees with measured artifacts")


def _numerical(claim: Claim, experiments: dict[str, ExperimentResult]) -> None:
    if not claim.experiment_ids or claim.value is None or not claim.metric:
        raise ValueError("numerical claim lacks metric, value, or experiments")
    if len(set(claim.experiment_ids)) != len(claim.experiment_ids):
        raise ValueError("duplicate numerical experiment links")
    rows = [experiments.get(i) for i in claim.experiment_ids]
    if any(r is None or r.status != "completed" or claim.metric not in r.metrics for r in rows):
        raise ValueError("numerical claim cites missing, failed, or incompatible experiments")
    completed = [r for r in rows if r is not None]
    units = {r.provenance.get("metric_units", {}).get(claim.metric, "scalar") for r in completed}
    if len(units) != 1:
        raise ValueError("aggregated measurements use inconsistent units")
    values = [r.metrics[claim.metric] for r in completed]
    if claim.aggregation == "mean":
        expected = sum(values) / len(values)
    elif claim.aggregation == "individual" and len(values) == 1:
        expected = values[0]
    elif claim.aggregation == "difference" and len(values) == 2:
        expected = values[0] - values[1]
    elif claim.aggregation == "relative_change" and len(values) == 2:
        if values[1] == 0:
            raise ValueError("relative change is undefined for a zero baseline")
        expected = (values[0] - values[1]) / abs(values[1])
    else:
        raise ValueError("unregistered numerical aggregation")
    source_unit = units.pop()
    if claim.aggregation == "relative_change":
        source_unit = "fraction"
    # A difference between percent-valued measurements is in percentage points.
    if claim.aggregation == "difference" and source_unit == "percent":
        source_unit = "percentage_points"
    elif claim.aggregation == "difference" and source_unit == "fraction":
        source_unit = "fraction_difference"
    _compare_literal(claim, expected, source_unit)


def _statistical(claim: Claim, experiments: dict[str, ExperimentResult]) -> None:
    analysis_run = experiments.get(claim.analysis_experiment_id)
    if analysis_run is None or analysis_run.status != "completed":
        raise ValueError("statistical claim requires a completed analysis execution")
    receipt = analysis_run.provenance.get("statistical_analyses", {}).get(claim.analysis_artifact)
    if (
        not isinstance(receipt, dict)
        or "error" in receipt
        or receipt.get("execution_id") != analysis_run.id
    ):
        raise ValueError("statistical claim has no valid execution-owned artifact receipt")
    data = _artifact_bytes(
        Path(analysis_run.provenance.get("workspace", "")), claim.analysis_artifact
    )
    if hashlib.sha256(data).hexdigest() != receipt.get("sha256"):
        raise ValueError("statistical artifact changed after execution")
    analysis = StatisticalAnalysis.model_validate_json(data)
    if analysis.model_dump() != receipt.get("analysis"):
        raise ValueError("statistical artifact disagrees with its execution receipt")
    if (
        not claim.experiment_ids
        or len(set(claim.experiment_ids)) != len(claim.experiment_ids)
        or set(claim.experiment_ids) != set(analysis.input_experiment_ids)
    ):
        raise ValueError("claim input experiments do not match the executed analysis")
    for eid in analysis.input_experiment_ids:
        item = experiments.get(eid)
        if (
            item is None
            or item.status != "completed"
            or analysis_input(item)["fingerprint"] != analysis.input_fingerprints.get(eid)
        ):
            raise ValueError("statistical input evidence is missing, failed, or changed")
    if claim.metric != analysis.metric or claim.statistic != analysis.statistic:
        raise ValueError("claim metric/statistic disagrees with executed analysis")
    _compare_literal(claim, analysis.value, inequalities=True)


def verify_claims(state: RunState, claims: list[Claim], source: Path) -> dict[str, Any]:
    """Check exact claim linkage; separate panels assess coverage and semantic validity."""
    experiments = {e.id: e for e in state.experiments}
    evidence = {e.id: e for e in state.evidence}
    issues: list[str] = []
    checked: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for claim in claims:
        reasons = []
        if claim.id in identifiers:
            reasons.append("duplicate claim identifier")
        identifiers.add(claim.id)
        if not claim.text.strip() or claim.text not in state.manuscript:
            reasons.append("claim text is not an exact manuscript span")
        try:
            if claim.kind == "numerical":
                _numerical(claim, experiments)
            elif claim.kind == "statistical":
                _statistical(claim, experiments)
            elif claim.kind == "citation":
                if not claim.evidence_ids:
                    reasons.append("citation claim has no retrieved evidence")
                for eid in claim.evidence_ids:
                    ref = evidence.get(eid)
                    if not ref or not (ref.abstract or ref.full_text or ref.excerpt):
                        reasons.append(f"citation lacks inspectable support: {eid}")
            elif claim.kind == "method":
                if not claim.code_paths:
                    reasons.append("method claim has no code locations")
                for relative in claim.code_paths:
                    path = source / relative
                    if (
                        path.is_symlink()
                        or not path.resolve().is_relative_to(source.resolve())
                        or not path.is_file()
                    ):
                        reasons.append("method cites nonexistent or unsafe code location")
            else:
                reasons.append("unknown claim type")
        except (OSError, ValueError, ValidationError) as exc:
            reasons.append(str(exc))
        issues.extend(f"{claim.id}: {reason}" for reason in reasons)
        checked.append({"claim": claim.model_dump(), "passed": not reasons, "issues": reasons})
    if not claims:
        issues.append("no claims extracted")
    return {
        "manuscript_sha256": hashlib.sha256(state.manuscript.encode()).hexdigest(),
        "claims": checked,
        "issues": issues,
        "passed": not issues,
        "coverage_verified": False,
    }


def declared_experiment_ids(manuscript: str) -> set[str]:
    return set(re.findall(r"\bexp-[a-f0-9]{12}\b", manuscript))


def attempt_summary(state: RunState) -> dict[str, Any]:
    experiments = state.experiments
    attempted = [
        i for i in state.ideas if i.status not in {"seed", "pending_novelty", "rejected_novelty"}
    ]
    return {
        "ideas_proposed": len(state.ideas),
        "ideas_attempted": len(attempted),
        "ideas_successful": sum(i.status in {"good", "superseded"} for i in attempted),
        "experiments_attempted": len(experiments) + int(state.pending_experiment is not None),
        "experiments_completed": sum(e.status == "completed" for e in experiments),
        "experiments_failed": sum(
            e.status in {"failed", "timeout", "cancelled"} for e in experiments
        ),
        "experiment_seconds": sum(e.duration_seconds for e in experiments),
        "statistical_significance": "not inferred from seeds or average improvement",
    }
