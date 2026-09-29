"""Claim-level evidence checks. LLM extraction is audited, never a numeric oracle."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from .contracts import Model, RunState


class Claim(Model):
    id: str
    kind: str
    text: str
    experiment_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    code_paths: list[str] = Field(default_factory=list)
    metric: str = ""
    value: float | None = None
    aggregation: str = "individual"
    rounding_tolerance: float = Field(default=0.000001, ge=0, le=0.05)
    analysis_artifact: str = ""


def verify_claims(state: RunState, claims: list[Claim], source: Path) -> dict[str, Any]:
    """Verify exact claim linkage; statistical claims need an executed analysis artifact.

    Method/citation entailment remains a separate independent model-panel judgment.
    A ledger cannot prove extraction completeness, so a separate coverage audit is required.
    """
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
        if claim.kind == "numerical":
            if not claim.experiment_ids or claim.value is None or not claim.metric:
                reasons.append("numerical claim lacks metric, value, or experiments")
            else:
                rows = [experiments.get(i) for i in claim.experiment_ids]
                if any(
                    r is None or r.status != "completed" or claim.metric not in r.metrics
                    for r in rows
                ):
                    reasons.append(
                        "numerical claim cites missing, failed, or incompatible experiments"
                    )
                else:
                    values = [r.metrics[claim.metric] for r in rows if r]
                    if claim.aggregation == "mean":
                        expected = sum(values) / len(values)
                    elif claim.aggregation == "individual" and len(values) == 1:
                        expected = values[0]
                    elif claim.aggregation == "difference" and len(values) == 2:
                        expected = values[0] - values[1]
                    else:
                        reasons.append("unregistered numerical aggregation")
                        expected = math.nan
                    if not math.isclose(
                        expected, claim.value, rel_tol=0, abs_tol=claim.rounding_tolerance
                    ):
                        reasons.append("reported number disagrees with measured artifacts")
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
        elif claim.kind == "statistical":
            if not claim.analysis_artifact or not claim.experiment_ids:
                reasons.append("statistical significance requires an executed statistical analysis")
            elif any(
                i not in experiments or experiments[i].status != "completed"
                for i in claim.experiment_ids
            ):
                reasons.append("statistical analysis has no completed execution")
            else:
                # Analysis evidence must live in a cited experiment workspace, not arbitrary prose.
                supported = False
                for eid in claim.experiment_ids:
                    workspace = Path(str(experiments[eid].provenance.get("workspace", "")))
                    artifact = workspace / claim.analysis_artifact
                    if (
                        workspace.is_dir()
                        and artifact.resolve().is_relative_to(workspace.resolve())
                        and artifact.is_file()
                        and not artifact.is_symlink()
                    ):
                        supported = True
                if not supported:
                    reasons.append("statistical analysis artifact is unavailable")
        else:
            reasons.append("unknown claim type")
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
