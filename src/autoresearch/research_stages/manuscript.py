"""Focused scientific stage handlers; the workflow owns dispatch and legal edges."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts import RunState, Stage

if TYPE_CHECKING:
    from ..agents import AgentRunner
    from ..config import ResearchConfig
    from ..engine import Engine


def write_manuscript(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    stage = s.stage
    out = agents.run(s, stage)
    if len(out.manuscript.strip()) < 100:
        raise ValueError("writer returned no substantive manuscript")
    s.manuscript = out.manuscript
    engine.store.artifact(s.id, "manuscript", f"manuscript-v{s.version}.md", s.manuscript)
    if stage == Stage.REVISE:
        s.counters["peer_revisions"] = s.counters.get("peer_revisions", 0) + 1
    s.stage = Stage.PEER_REVIEW


def peer_review(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    out = engine._judge(s, agents)
    if out.score is None:
        raise ValueError("peer reviewer must give a numeric score")
    s.reviews.append(
        {
            "kind": "peer",
            "score": out.score,
            "feedback": out.feedback,
            "concerns": out.concerns,
            "version": s.version,
            "review": out.model_dump(),
        }
    )
    if (out.score >= p.review_threshold and out.decision == "accept") or s.counters.get(
        "peer_revisions", 0
    ) >= p.peer_rounds - 1:
        s.stage = Stage.META_REVIEW
    else:
        s.stage = Stage.REBUTTAL_PLAN


def meta_review(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    out = engine._judge(s, agents)
    s.reviews.append(
        {
            "kind": "meta",
            "decision": out.decision,
            "feedback": out.feedback,
            "version": s.version,
        }
    )
    if out.decision == "accept":
        s.outcome = "simulated_meta_acceptance"
        s.stage = Stage.INTEGRITY
    elif s.counters.get("meta_refinements", 0) < p.meta_rounds:
        s.counters["meta_refinements"] = s.counters.get("meta_refinements", 0) + 1
        s.stage = Stage.META_REFINE
    else:
        s.outcome = "meta_refinement_limit_previous_best_retained"
        s.stage = Stage.INTEGRITY


def complete(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    s.status = "completed"
