"""Focused scientific stage handlers; the workflow owns dispatch and legal edges."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..contracts import Evidence, RunState, Stage
from ..literature import Literature, novelty_coverage
from ..workflow import get_workflow

if TYPE_CHECKING:
    from ..agents import AgentRunner
    from ..config import ResearchConfig
    from ..engine import Engine


def extract_limitations(
    engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner
) -> None:
    stage = s.stage
    context: dict[str, Any] = {}
    if c.mode == "live":
        retriever = engine.literature or Literature(c)
        refs = retriever.search(s.title + " " + s.objective[:1000], c.pipeline.novelty_references)
        known = {e.id: e for e in s.evidence}
        known.update({e.id: e for e in refs})
        s.evidence = list(known.values())
        context = {
            "retrieved": [e.model_dump() for e in refs],
            "search_reports": getattr(retriever, "search_history", []),
        }
        engine.store.artifact(
            s.id,
            "limitation_evidence",
            f"limitations-v{s.version}.json",
            json.dumps(context, default=str),
        )
        if not refs:
            raise ValueError("limitation extraction requires retrieved sources")
    output = agents.run(s, stage, context)
    if not output.limitations:
        raise ValueError("limitation extractor returned no limitations")
    s.limitations = list(dict.fromkeys([*s.limitations, *output.limitations]))
    s.stage = Stage.VERIFY_LIMITATIONS


def verify_limitations(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    out = engine._judge(s, agents)
    s.counters["limitations"] = s.counters.get("limitations", 0) + 1
    if out.decision == "accept":
        s.stage = Stage.GENERATE_IDEAS
    elif out.decision == "reject" or s.counters["limitations"] >= p.limitation_rounds:
        engine._stop(s, "limitations_not_verified", failed=True)
    else:
        s.stage = Stage.LIMITATIONS


def generate_ideas(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    stage = s.stage
    needed = p.seed_count - sum(i.status == "seed" for i in s.ideas)
    if needed <= 0:
        s.stage = Stage.FILTER_IDEAS
        return
    # Published sequence: generate -> check novelty -> expand with that feedback.
    out = agents.run(s, stage, {"requested_ideas": 1, "remaining_seed_slots": needed})
    added: list[str] = []
    if out.decision == "accept":
        added = engine._add_ideas(s, out.ideas[:needed], evolved=False)
        for idea in s.ideas:
            if idea.id in added:
                idea.status = "pending_novelty"
    else:
        s.feedback = out.feedback or out.summary
    s.counters["generation"] = s.counters.get("generation", 0) + 1
    if added:
        s.stage = Stage.NOVELTY
    elif s.counters["generation"] >= p.generation_rounds:
        engine._stop(s, "seed_pool_exhausted", failed=True)


def assess_novelty(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    pending = [idea for idea in s.ideas if idea.status == "pending_novelty"]
    if not pending:
        raise ValueError("novelty requires newly proposed candidates")
    if c.mode == "demo":
        s.evidence = [
            Evidence(
                id=f"demo-{i}",
                title="Synthetic fixture reference (not novelty evidence)",
                url=f"https://example.org/fixture/{i}",
            )
            for i in range(p.novelty_references)
        ]
    else:
        retriever = engine.literature or Literature(c)
        found: dict[str, Evidence] = {e.id: e for e in s.evidence}
        for idea in pending:
            retrieved: dict[str, Evidence] = {}
            queries = [
                idea.title + " " + idea.hypothesis,
                idea.hypothesis,
                idea.title + " alternative prior methods limitations",
            ][: p.novelty_queries]
            for query in queries:
                retrieved.update({e.id: e for e in retriever.search(query, p.novelty_references)})
            refs = list(retrieved.values())
            reports = getattr(retriever, "search_history", [])
            coverage = novelty_coverage(refs, reports, minimum=c.literature.min_novelty_sources)
            s.memory.append(
                {
                    "kind": "novelty_search",
                    "idea": idea.id,
                    "coverage": coverage,
                    "source_ids": [e.id for e in refs],
                }
            )
            engine.store.event(
                s.id, "literature_coverage", s.stage, {"idea": idea.id, "coverage": coverage}
            )
            engine.store.artifact(
                s.id,
                "novelty_search",
                f"novelty-{idea.id}-v{s.version}.json",
                json.dumps(
                    {
                        "queries": queries,
                        "sources": [e.model_dump() for e in refs],
                        "reports": reports,
                        "exhaustive": False,
                    },
                    indent=2,
                    default=str,
                ),
            )
            if len(refs) < p.novelty_references:
                raise ValueError(
                    f"novelty search returned {len(refs)} sources; configured minimum is {p.novelty_references}. Coverage is insufficient, not evidence of novelty."
                )
            if sum(bool(e.abstract or e.full_text or e.excerpt) for e in refs) < min(
                4, p.novelty_references
            ):
                raise ValueError("novelty requires inspectable paper content, not metadata alone")
            if not coverage["sufficient_for_assessment"]:
                raise ValueError(
                    "novelty search lacks independent inspectable evidence; see saved coverage report"
                )
            idea.evidence = [e.id for e in refs]
            found.update({e.id: e for e in refs})
        s.evidence = list(found.values())
    out = engine._judge(
        s,
        agents,
        {
            "active_seed_ids": [idea.id for idea in pending],
            "task": get_workflow().nodes[s.stage].instructions["assessment"],
        },
    )
    if out.decision == "accept":
        if not {idea.id for idea in pending}.issubset(out.novelty_scores) or not set(
            out.novelty_scores
        ).issubset({idea.id for idea in s.ideas}):
            raise ValueError("novelty checker must score each new candidate without unknown ideas")
        if c.mode != "demo" and (
            len(set(out.evidence_ids)) < p.novelty_references
            or not set(out.evidence_ids).issubset({e.id for e in s.evidence})
        ):
            raise ValueError("novelty checker must cite retrieved reference evidence")
        for idea in pending:
            idea.novelty, idea.status = out.novelty_scores[idea.id], "seed"
    else:
        for idea in pending:
            idea.status = "rejected_novelty"
    s.ideas.sort(key=lambda idea: idea.novelty, reverse=True)
    if sum(idea.status == "seed" for idea in s.ideas) >= p.seed_count:
        s.stage = Stage.FILTER_IDEAS
    elif s.counters.get("generation", 0) >= p.generation_rounds:
        engine._stop(s, "seed_pool_exhausted", failed=True)
    else:
        s.stage = Stage.GENERATE_IDEAS


def filter_ideas(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    active = sorted(
        (idea for idea in s.ideas if idea.status == "seed"),
        key=lambda idea: idea.novelty,
        reverse=True,
    )
    if len(active) < p.initial_candidates:
        raise ValueError("filtering requires enough active seed candidates")
    out = engine._judge(s, agents, {"active_seed_ids": [idea.id for idea in active]})
    if out.decision == "accept":
        s.queue = [i.id for i in active[: p.initial_candidates]]
        s.stage = Stage.BASELINE
    elif out.decision == "refine" and s.counters.get("generation", 0) < p.generation_rounds:
        for idea in active:
            idea.status = "rejected_novelty"
        s.stage = Stage.GENERATE_IDEAS
    else:
        engine._stop(s, "novelty_not_verified", failed=True)


def evolve(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    stage = s.stage
    out = agents.run(s, stage, {"requested_ideas": p.evolved_per_round})
    if out.decision != "accept":
        raise ValueError("evolver proposals did not pass the configured agent panel")
    ids = engine._add_ideas(s, out.ideas[: p.evolved_per_round], evolved=True)
    if not ids:
        raise ValueError("evolver returned no distinct hypotheses")
    fresh = [i.id for i in s.ideas if i.status == "seed"][: p.exploration_per_round]
    s.queue = ids + fresh
    engine._next_candidate(s)
