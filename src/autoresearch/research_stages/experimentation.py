"""Focused scientific stage handlers; the workflow owns dispatch and legal edges."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from ..contracts import AgentOutput, RunState, Stage

if TYPE_CHECKING:
    from ..agents import AgentRunner
    from ..config import ResearchConfig
    from ..engine import Engine


def criticize_candidate(
    engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner
) -> None:
    p = c.pipeline
    stage = s.stage
    out = engine._judge(s, agents)
    current = engine._idea(s)
    ref = s.baseline if stage == Stage.SUBSET_CRITIC else c.project.sota
    if out.decision == "accept" and not engine._better(current.metrics, ref, c):
        out.decision = "refine"
        s.feedback += "\nMeasured metrics do not establish strict, consistent improvement."
    count_key = "subset_engineering" if stage == Stage.SUBSET_CRITIC else "full_engineering"
    if out.decision == "accept":
        if stage == Stage.SUBSET_CRITIC:
            current.status, s.stage = "subset_good", Stage.FULL
        else:
            current.status = "good"
            engine._finish_candidate(s, c)
    elif out.decision == "refine" and s.counters.get(count_key, 0) < p.engineering_rounds:
        s.counters[count_key] = s.counters.get(count_key, 0) + 1
        s.stage = Stage.SUBSET_ENGINEER if stage == Stage.SUBSET_CRITIC else Stage.FULL_ENGINEER
    else:
        current.status = "bad"
        engine._finish_candidate(s, c)


def select_candidate(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    out = engine._judge(s, agents)
    good = {i.id for i in s.ideas if i.status == "good"}
    if out.decision != "accept" or out.selected_id not in good:
        raise ValueError("selector must independently accept a full-benchmark successful candidate")
    s.selected_idea = s.current_idea = out.selected_id
    s.stage = Stage.ABLATION_PLAN


def plan_supplementary(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    stage = s.stage
    out = agents.run(s, stage)
    if not out.plans or any(not isinstance(plan.get("question"), str) for plan in out.plans):
        raise ValueError("planner must return nonempty executable plans with questions")
    s.plans, s.plan_index = out.plans, 0
    s.stage = Stage.ABLATION if stage == Stage.ABLATION_PLAN else Stage.REBUTTAL


def criticize_ablation(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    p = c.pipeline
    out = engine._judge(s, agents)
    if c.mode == "live" and out.decision == "accept":
        # Keep the selected/frontier judgment and every accepting panel member;
        # a tied selection cannot discard another critic's missing evidence.
        assessments = [out.structured.get("attribution", {})]
        panel = out.structured.get("panel_outputs", [])
        if not isinstance(panel, list):
            assessments.append(None)
        else:
            for member in panel:
                if not isinstance(member, dict):
                    assessments.append(None)
                elif member.get("decision") == "accept":
                    structured = member.get("structured", {})
                    assessments.append(
                        structured.get("attribution") if isinstance(structured, dict) else None
                    )
        eligible = {
            result.id
            for result in s.experiments
            if result.status == "completed"
            and result.provenance.get("kind") == "ablation"
            and result.provenance.get("selected_idea") == s.selected_idea
        }
        supported = True
        for attribution in assessments:
            cited = attribution.get("experiment_ids", []) if isinstance(attribution, dict) else []
            valid = (
                isinstance(attribution, dict)
                and attribution.get("supported") is True
                and attribution.get("generic_controls_only") is False
                and all(
                    isinstance(attribution.get(key), str) and attribution[key].strip()
                    for key in ("mechanism", "rationale")
                )
                and isinstance(cited, list)
                and bool(cited)
                and all(
                    isinstance(identifier, str) and identifier in eligible for identifier in cited
                )
            )
            supported = supported and valid
        s.memory.append(
            {
                "kind": "ablation_attribution",
                "idea": s.selected_idea,
                "supported": supported,
                "version": s.version,
                "assessments": assessments,
            }
        )
        if not supported:
            out.decision = "refine"
            s.feedback += "\nAblation evidence does not attribute gain to the proposed mechanism; generic controls alone are insufficient."
    if c.mode == "demo" and out.decision == "accept":
        s.memory.append(
            {
                "kind": "ablation_attribution",
                "idea": s.selected_idea,
                "supported": True,
                "version": s.version,
                "synthetic": True,
            }
        )
    if out.decision == "accept":
        s.stage = Stage.DRAFT
    elif s.counters.get("ablation_refinements", 0) >= p.ablation_rounds:
        engine._stop(s, "ablation_gain_not_attributed", failed=True)
    else:
        s.counters["ablation_refinements"] = s.counters.get("ablation_refinements", 0) + 1
        s.stage = Stage.ABLATION_REFINE


def compare_refinement(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    if s.candidate_update is None or s.candidate_update.id == s.selected_idea:
        raise ValueError("comparison requires a distinct archived refinement hypothesis")
    out = engine._judge(
        s,
        agents,
        {
            "previous_best": engine._idea(s, s.selected_idea).model_dump(),
            "proposed": s.candidate_update.model_dump() if s.candidate_update else None,
        },
    )
    old = engine._idea(s, s.selected_idea)
    improved = (
        s.candidate_update is not None
        and out.decision == "accept"
        and engine._better(s.candidate_update.metrics, old.metrics, c)
    )
    s.memory.append(
        {
            "kind": "refinement_comparison",
            "incumbent": old.model_dump(),
            "proposal": s.candidate_update.model_dump() if s.candidate_update else None,
            "accepted": improved,
            "feedback": s.feedback,
            "origin": s.comparison_origin,
        }
    )
    proposal = s.candidate_update
    if proposal is not None:
        proposal.status = "good" if improved else "rejected_refinement"
        # Pending refinements may already be archived; never duplicate their ID.
        s.ideas = [idea for idea in s.ideas if idea.id != proposal.id] + [proposal]
        decision = {
            "kind": "candidate_decision",
            "idea": proposal.id,
            "decision": proposal.status,
            "origin": s.comparison_origin,
            "round": proposal.round,
            "hypothesis": proposal.model_dump(),
            "previous_best": old.id,
            "critic_decision": out.decision,
            "feedback": s.feedback,
            "metrics": proposal.metrics,
            "workspace": proposal.workspace,
            "experiment_ids": engine._workspace_experiment_ids(s, proposal.workspace),
        }
        s.memory.append(decision)
        engine.store.artifact(
            s.id,
            "refinement_decision",
            f"refinement-{proposal.id}.json",
            json.dumps(decision, indent=2),
        )
    if improved and proposal:
        old.status = "superseded"
        s.selected_idea = s.current_idea = s.candidate_update.id
        s.candidate_update = None
        s.counters["peer_revisions"] = 0
        if s.comparison_origin == "meta":
            s.counters["ablation_refinements"] = 0
        s.stage = Stage.ABLATION_PLAN
    elif s.comparison_origin == "meta":
        s.candidate_update = None
        s.outcome = "previous_best_retained_meta_refinement_not_superior"
        s.stage = Stage.INTEGRITY
    else:
        s.candidate_update = None
        # Reassess retained evidence; an exhausted refinement is not approval.
        s.stage = Stage.ABLATION_CRITIC


def execute(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    engine._experiment(s, c, agents)


def finish_batch(
    engine: Engine,
    s: RunState,
    c: ResearchConfig,
    successful: bool,
    metrics: dict[str, float],
    workspace: str,
    proposal: AgentOutput | None = None,
) -> None:
    stage = s.stage
    if stage == Stage.BASELINE:
        if not successful:
            s.counters["baseline_repairs"] = s.counters.get("baseline_repairs", 0) + 1
            s.feedback = "Baseline execution failed. Repair the implementation using recorded diagnostics without changing the operator's baseline command or evaluation protocol."
            if s.counters["baseline_repairs"] <= c.pipeline.engineering_rounds:
                return
            raise ValueError(
                "baseline reproduction failed after execution repairs; inspect failure and intervene"
            )
        if c.project.baseline_expected and any(
            abs(metrics[k] - v) > c.project.reproduction_tolerance * max(abs(v), 1e-12)
            for k, v in c.project.baseline_expected.items()
        ):
            raise ValueError("reproduced baseline outside configured tolerance")
        s.baseline = metrics
        s.memory.append(
            {"kind": "baseline_workspace", "workspace": str(engine._pristine_input(s, workspace))}
        )
        engine._next_candidate(s)
    elif stage in {Stage.SUBSET, Stage.SUBSET_ENGINEER, Stage.FULL, Stage.FULL_ENGINEER}:
        idea = engine._idea(s)
        idea.metrics, idea.workspace = metrics, workspace
        s.feedback = (
            "Execution failed; inspect diagnostic traces and repair."
            if not successful
            else s.feedback
        )
        s.stage = (
            Stage.SUBSET_CRITIC
            if stage in {Stage.SUBSET, Stage.SUBSET_ENGINEER}
            else Stage.FULL_CRITIC
        )
    elif stage in {Stage.ABLATION, Stage.REBUTTAL}:
        if not successful:
            s.memory.append(
                {
                    "kind": "supplementary_failure",
                    "stage": stage.value,
                    "plan": s.plans[s.plan_index],
                    "feedback": "Retain and disclose failed evidence; do not invent measurements.",
                }
            )
            s.feedback = "The supplementary experiment failed. Repair this plan's implementation using diagnostic history; do not invent missing measurements."
            s.counters["supplementary_repairs"] = s.counters.get("supplementary_repairs", 0) + 1
            if s.counters["supplementary_repairs"] > c.pipeline.engineering_rounds:
                raise ValueError(
                    "supplementary experiment failed after execution repairs; unresolved evidence blocks advancement"
                )
            return
        s.counters["supplementary_repairs"] = 0
        s.plan_index += 1
        if s.plan_index >= len(s.plans):
            s.stage = Stage.ABLATION_CRITIC if stage == Stage.ABLATION else Stage.REVISE
    elif stage in {Stage.ABLATION_REFINE, Stage.META_REFINE}:
        previous = engine._idea(s, s.selected_idea)
        if proposal and len(proposal.ideas) == 1:
            s.candidate_update = proposal.ideas[0].model_copy(deep=True)
        elif c.mode == "demo":
            s.candidate_update = previous.model_copy(deep=True)
            s.candidate_update.rationale = (
                "Synthetic fixture refinement; hypothesis unchanged by scripted coder."
            )
        else:
            raise ValueError("refined implementation lacks its revised scientific hypothesis")
        s.candidate_update.status = "pending_comparison" if successful else "bad"
        s.candidate_update.round = s.round
        s.candidate_update.id = f"refined-{uuid.uuid4().hex[:10]}"
        s.candidate_update.parents = [previous.id]
        s.candidate_update.metrics, s.candidate_update.workspace = metrics, workspace
        s.comparison_origin = "meta" if stage == Stage.META_REFINE else "ablation"
        # Archive the hypothesis before comparison so interrupted/rejected attempts
        # remain part of the denominator and available to later evolution.
        s.ideas.append(s.candidate_update.model_copy(deep=True))
        s.memory.append(
            {
                "kind": "refinement_proposed",
                "origin": s.comparison_origin,
                "hypothesis": s.candidate_update.model_dump(),
                "experiment_ids": engine._workspace_experiment_ids(s, workspace),
            }
        )
        s.stage = Stage.COMPARE


def candidate_completed(engine: Engine, s: RunState, c: ResearchConfig) -> None:
    idea = engine._idea(s)
    s.memory.append(
        {
            "kind": "candidate_decision",
            "idea": idea.id,
            "decision": idea.status,
            "round": s.round,
            "metrics": idea.metrics,
            "feedback": s.feedback,
            "workspace": idea.workspace,
        }
    )
    if sum(i.status == "good" for i in s.ideas) >= c.pipeline.successful_ideas:
        s.stage = Stage.SELECT
    elif s.queue:
        engine._next_candidate(s)
    elif s.round + 1 < c.pipeline.experiment_rounds:
        s.round += 1
        s.stage = Stage.EVOLVE
    elif any(i.status == "good" for i in s.ideas):
        s.stage = Stage.SELECT
    else:
        engine._stop(s, "no_successful_full_benchmark_idea", failed=True)


def next_candidate(s: RunState) -> None:
    if not s.queue:
        raise ValueError("candidate queue is empty")
    s.current_idea = s.queue.pop(0)
    current = next((idea for idea in s.ideas if idea.id == s.current_idea), None)
    if current is None:
        raise ValueError("current/selected candidate does not exist")
    current.status = "evaluating"
    s.counters["subset_engineering"] = s.counters["full_engineering"] = 0
    s.stage = Stage.SUBSET


def strictly_better(
    metrics: dict[str, float], reference: dict[str, float], c: ResearchConfig
) -> bool:
    if not reference or not metrics:
        return False
    gains = []
    for key, direction in c.project.metrics.items():
        if key not in reference or key not in metrics:
            return False
        delta = (metrics[key] - reference[key]) * (1 if direction == "max" else -1)
        gains.append(delta)
        if delta < 0 and c.project.result_preference == "pareto":
            return False
    if c.project.result_preference == "scientific_critic":
        # This is only a necessary measured-evidence condition. Every caller also
        # requires an independent stage critic/comparison acceptance with rationale.
        return any(gain > c.project.min_improvement for gain in gains)
    primary = c.project.primary_metric
    delta = (metrics[primary] - reference[primary]) * (
        1 if c.project.metrics[primary] == "max" else -1
    )
    return delta > c.project.min_improvement
