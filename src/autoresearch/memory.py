"""Explicit model views over the complete, privately retained research checkpoint.

Projection never mutates or truncates the durable scientific record. Held-out
judgments are evaluation artifacts, excluded from every optimization view.
"""

from __future__ import annotations

from typing import Any

from .contracts import RunState


def is_heldout(record: dict[str, Any]) -> bool:
    return record.get("optimization_feedback") is False or any(
        record.get(key) in {"heldout", "heldout_review"} for key in ("kind", "role", "stage")
    )


def research_view(state: RunState, *, heldout: bool = False) -> dict[str, Any]:
    view = state.model_dump(
        mode="json", exclude={"version", "created_at", "updated_at", "status", "error"}
    )
    if heldout:
        return {
            key: view[key]
            for key in (
                "id",
                "title",
                "objective",
                "manuscript",
                "evidence",
                "experiments",
                "selected_idea",
            )
        }
    view["reviews"] = [item for item in view["reviews"] if not is_heldout(item)]
    view["memory"] = [item for item in view["memory"] if not is_heldout(item)]
    return view


def optimization_state(state: RunState) -> RunState:
    """Preserve the typed writer interface while shielding held-out review records."""
    return state.model_copy(
        deep=True,
        update={
            "reviews": [item for item in state.reviews if not is_heldout(item)],
            "memory": [item for item in state.memory if not is_heldout(item)],
        },
    )
