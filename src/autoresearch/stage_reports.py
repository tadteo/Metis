"""Deterministic checkpoint reports; recorded changes never imply scientific acceptance."""

import hashlib
from typing import Any

from .contracts import RunState

REPORT_KINDS = {
    "transition",
    "stage_error",
    "workflow_violation",
    "budget_exhausted",
    "coding_pending",
}


def stage_report(
    before: RunState,
    after: RunState,
    kind: str,
    event_seq: int,
    *,
    synthetic: bool,
    reason: str = "",
) -> dict[str, Any]:
    previous = before.model_dump(mode="json")
    current = after.model_dump(mode="json")
    changes: dict[str, Any] = {}
    # Preserve changed records as well as appended ones (e.g. an idea's rejection).
    for field in ("limitations", "ideas", "experiments", "evidence", "plans", "reviews", "memory"):
        records = [item for item in current[field] if item not in previous[field]]
        if records:
            changes[field] = records
    for field in (
        "research_brief",
        "research_protocol",
        "baseline",
        "active_output",
        "candidate_update",
    ):
        if current[field] and current[field] != previous[field]:
            changes[field] = current[field]
    if after.manuscript != before.manuscript:
        content = after.manuscript.encode()
        changes["manuscript"] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }
    return {
        "schema_version": 1,
        "stage": before.stage.value,
        "checkpoint": after.version,
        "event_seq": event_seq,
        "kind": kind,
        "status": after.status,
        "synthetic": synthetic,
        "idea": before.current_idea,
        "next_idea": after.current_idea,
        "reason": reason,
        "round": before.round,
        "next_stage": after.stage.value,
        "outcome": after.outcome if after.outcome != before.outcome else "",
        "feedback": after.feedback if after.feedback != before.feedback else "",
        "error": after.error
        if kind in {"stage_error", "workflow_violation", "budget_exhausted"}
        else "",
        "changes": changes,
    }
