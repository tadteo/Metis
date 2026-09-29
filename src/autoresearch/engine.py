"""Checkpointed ScientistTwo workflow, preserving criticism and scientific feedback loops."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
import re
import shutil
import stat
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .agents import AgentRunner
from .coding import CodingPending
from .config import ResearchConfig
from .contracts import (
    AgentOutput,
    Evidence,
    ExperimentResult,
    ExperimentSpec,
    Idea,
    RunState,
    Stage,
)
from .demo import BENCHMARK
from .execution import Executor, _parent, _read, _write
from .integrity import Claim, attempt_summary, verify_claims
from .literature import Literature, novelty_coverage
from .privacy import redact
from .providers import Provider
from .references import audit_references
from .source_policy import source_is_excluded
from .store import BudgetExceeded, Store, now

EXPERIMENT_STAGES = {
    Stage.BASELINE,
    Stage.SUBSET,
    Stage.SUBSET_ENGINEER,
    Stage.FULL,
    Stage.FULL_ENGINEER,
    Stage.ABLATION,
    Stage.ABLATION_REFINE,
    Stage.REBUTTAL,
    Stage.META_REFINE,
}
TERMINAL = {"completed", "failed", "stopped"}


class Engine:
    def __init__(
        self,
        store: Store,
        config: ResearchConfig | None = None,
        *,
        provider: Provider | None = None,
        executor: Executor | None = None,
        literature: Literature | None = None,
        stage_handlers: Mapping[Stage, Callable[[RunState, ResearchConfig, AgentRunner], None]]
        | None = None,
        runner_factory: Callable[[Store, ResearchConfig], AgentRunner] | None = None,
    ):
        self.store, self.config = store, config or ResearchConfig()
        self.provider, self.executor, self.literature = provider, executor, literature
        self.stage_handlers = dict(stage_handlers or {})
        self.runner_factory = runner_factory

    def create(self, title: str, objective: str, demo: bool = False) -> RunState:
        if (
            not title.strip()
            or not objective.strip()
            or len(title) > 200
            or len(objective) > 100000
        ):
            raise ValueError("title and objective must be nonempty and within length limits")
        config = self.config.model_copy(deep=True)
        state = RunState(
            id=uuid.uuid4().hex[:12],
            title=title,
            objective=objective,
            created_at=now(),
            updated_at=now(),
        )
        if demo or config.mode == "demo":
            config.mode = "demo"
            config.role_commands = {}
            config.search_enabled = False
            config.execution.backend = "local"
            config.execution.allow_local = True
            config.project.source_dir = ""
            config.project.sota = {"score": 0.5}
            config.project.metrics = {"score": "max"}
            config.project.primary_metric = "score"
            config.project.baseline_argv = []
            config.project.evaluator_argv = []
            config.project.protected_paths = []
            config.project.specification = "Offline synthetic regression fixture; scripted judgments are not scientific validation."
            config.project.seeds = [0, 1]
            config.references = []
        self.store.create(state, config)
        source = self.store.run_dir(state.id) / "source"
        source.mkdir(mode=0o700)
        if config.mode == "demo":
            (source / "benchmark.py").write_text(BENCHMARK)
        elif config.project.source_dir:
            original = Path(config.project.source_dir).expanduser().resolve(strict=True)
            if not original.is_dir():
                raise ValueError("source_dir must be a directory")
            self._copy_source(original, source, config.project.include)
        self.store.artifact(
            state.id, "configuration", "config.json", config.model_dump_json(indent=2)
        )
        return state

    def pause(self, run_id: str) -> None:
        self.store.set_paused(run_id, True)
        self.store.event(run_id, "pause_requested", self.store.get_run(run_id).stage, {})

    def resume(self, run_id: str) -> RunState:
        self.store.set_paused(run_id, False)
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            if state.status not in TERMINAL:
                state.status, state.error = "ready", ""
                self.store.save(state, "resumed")
            return state

    def cancel_experiment(self, run_id: str) -> RunState:
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            config = self.store.get_config(run_id)
            if not state.pending_experiment or not state.pending_job_id:
                raise ValueError(
                    "no resumable scheduler job to cancel; request pause for synchronous execution"
                )
            (self.executor or Executor(config.execution)).cancel(state.pending_job_id)
            result = ExperimentResult(
                id=state.pending_experiment.id,
                status="cancelled",
                job_id=state.pending_job_id,
                stderr="Cancelled explicitly by operator",
                provenance={
                    "kind": state.stage.value,
                    "seed": state.pending_experiment.seed,
                    "workspace": state.pending_experiment.workspace,
                },
            )
            state.experiments.append(result)
            state.memory.append(
                {
                    "kind": "experiment",
                    "status": "cancelled",
                    "id": result.id,
                    "stage": state.stage.value,
                    "idea": state.current_idea,
                    "reason": "operator cancellation",
                }
            )
            state.pending_experiment, state.pending_job_id = None, None
            state.batch_results, state.active_output = [], None
            state.status = "paused"
            self.store.set_paused(run_id, True)
            self.store.save(
                state, "experiment_cancelled", {"id": result.id, "job_id": result.job_id}
            )
            return state

    def intervene(self, run_id: str, note: str, stage: str | None = None) -> RunState:
        if not note.strip() or len(note) > 100000:
            raise ValueError("intervention must contain a note of at most 100000 characters")
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            if state.pending_experiment:
                raise ValueError("wait for or cancel the pending experiment before intervention")
            state.feedback = note
            state.memory.append(
                {
                    "kind": "human_intervention",
                    "note": note,
                    "stage": state.stage.value,
                    "timestamp": now(),
                }
            )
            if stage:
                target = Stage(stage)
                if target == Stage.COMPLETE:
                    raise ValueError("completion requires integrity checks; cannot force complete")
                if target in {
                    Stage.SELECT,
                    Stage.ABLATION_PLAN,
                    Stage.DRAFT,
                    Stage.INTEGRITY,
                } and not any(i.status == "good" for i in state.ideas):
                    raise ValueError("this stage requires a full-benchmark successful idea")
                if (
                    target in EXPERIMENT_STAGES
                    and target != Stage.BASELINE
                    and not state.current_idea
                    and not state.selected_idea
                ):
                    raise ValueError("this stage requires a candidate idea")
                state.stage = target
                state.active_output = None
                state.batch_results = []
            state.status, state.error = "ready", ""
            self.store.save(state, "human_intervention", {"note": note, "stage": stage})
            return state

    def run(self, run_id: str, max_steps: int | None = None) -> RunState:
        steps = 0
        while max_steps is None or steps < max_steps:
            state = self.step(run_id)
            steps += 1
            if state.status in TERMINAL | {"blocked", "budget_exhausted", "paused"}:
                return state
            if state.status == "waiting":
                time.sleep(min(self.store.get_config(run_id).execution.slurm_poll_seconds, 10))
        return self.store.get_run(run_id)

    def step(self, run_id: str) -> RunState:
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            config = self.store.get_config(run_id)
            if state.status in TERMINAL:
                return state
            if self.store.is_paused(run_id):
                state.status = "paused"
                self.store.save(state)
                return state
            # Errors require explicit resume, so a watch loop cannot silently retry paid work.
            if state.status in {"blocked", "budget_exhausted"}:
                return state
            runner = (
                self.runner_factory(self.store, config)
                if self.runner_factory
                else AgentRunner(self.store, config, self.provider)
            )
            previous = state.stage
            try:
                elapsed = (
                    datetime.fromisoformat(now()) - datetime.fromisoformat(state.created_at)
                ).total_seconds()
                if elapsed > config.budget.wall_seconds:
                    raise BudgetExceeded("wall-clock budget reached")
                state.status = "running"
                handler = self.stage_handlers.get(state.stage)
                if handler:
                    handler(state, config, runner)
                else:
                    self._advance(state, config, runner)
                if state.status == "running":
                    state.status = "ready"
                self.store.save(
                    state,
                    "transition",
                    {
                        "from": previous.value,
                        "to": state.stage.value,
                        "status": state.status,
                        "outcome": state.outcome,
                        "idea": state.current_idea,
                    },
                )
            except CodingPending as exc:
                state.status = "paused" if self.store.is_paused(run_id) else "waiting"
                self.store.save(state, "coding_pending", {"reason": str(exc)})
            except BudgetExceeded as exc:
                state.status, state.error = "budget_exhausted", str(exc)
                self.store.save(state, "budget_exhausted", {"reason": state.error})
            except Exception as exc:
                state.status = "blocked"
                state.error = str(
                    redact(f"{type(exc).__name__}: {exc}", config.privacy.redact_patterns)
                )[:2000]
                self.store.save(
                    state, "stage_error", {"error": state.error, "stage": previous.value}
                )
            return state

    def _advance(self, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
        p, stage = c.pipeline, s.stage
        if stage in EXPERIMENT_STAGES:
            self._experiment(s, c, agents)
            return
        if stage == Stage.LIMITATIONS:
            context: dict[str, Any] = {}
            if c.mode == "live":
                retriever = self.literature or Literature(c)
                refs = retriever.search(s.title + " " + s.objective[:1000], c.pipeline.novelty_references)
                known = {e.id: e for e in s.evidence}
                known.update({e.id: e for e in refs})
                s.evidence = list(known.values())
                context = {"retrieved": [e.model_dump() for e in refs], "search_reports": getattr(retriever, "search_history", [])}
                self.store.artifact(s.id, "limitation_evidence", f"limitations-v{s.version}.json", json.dumps(context, default=str))
                if not refs:
                    raise ValueError("limitation extraction requires retrieved sources")
            output = agents.run(s, stage, context)
            if not output.limitations:
                raise ValueError("limitation extractor returned no limitations")
            s.limitations = list(dict.fromkeys([*s.limitations, *output.limitations]))
            s.stage = Stage.VERIFY_LIMITATIONS
        elif stage == Stage.VERIFY_LIMITATIONS:
            out = self._judge(s, agents)
            s.counters["limitations"] = s.counters.get("limitations", 0) + 1
            if out.decision == "accept":
                s.stage = Stage.GENERATE_IDEAS
            elif out.decision == "reject" or s.counters["limitations"] >= p.limitation_rounds:
                self._stop(s, "limitations_not_verified", failed=True)
            else:
                s.stage = Stage.LIMITATIONS
        elif stage == Stage.GENERATE_IDEAS:
            needed = p.seed_count - sum(i.status == "seed" for i in s.ideas)
            if needed <= 0:
                s.stage = Stage.FILTER_IDEAS
                return
            # Published sequence: generate -> check novelty -> expand with that feedback.
            out = agents.run(s, stage, {"requested_ideas": 1, "remaining_seed_slots": needed})
            added: list[str] = []
            if out.decision == "accept":
                added = self._add_ideas(s, out.ideas[:needed], evolved=False)
                for idea in s.ideas:
                    if idea.id in added:
                        idea.status = "pending_novelty"
            else:
                s.feedback = out.feedback or out.summary
            s.counters["generation"] = s.counters.get("generation", 0) + 1
            if added:
                s.stage = Stage.NOVELTY
            elif s.counters["generation"] >= p.generation_rounds:
                self._stop(s, "seed_pool_exhausted", failed=True)
        elif stage == Stage.NOVELTY:
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
                retriever = self.literature or Literature(c)
                found: dict[str, Evidence] = {e.id: e for e in s.evidence}
                for idea in pending:
                    retrieved: dict[str, Evidence] = {}
                    for query in (idea.title, idea.hypothesis, idea.title + " alternative prior methods limitations"):
                        retrieved.update({e.id: e for e in retriever.search(query, p.novelty_references)})
                    refs = list(retrieved.values())
                    reports = getattr(retriever, "search_history", [])
                    coverage = novelty_coverage(refs, reports)
                    s.memory.append({"kind": "novelty_search", "idea": idea.id, "coverage": coverage, "source_ids": [e.id for e in refs]})
                    self.store.artifact(s.id, "novelty_search", f"novelty-{idea.id}-v{s.version}.json", json.dumps({"queries": [idea.title, idea.hypothesis, idea.title + " alternative prior methods limitations"], "sources": [e.model_dump() for e in refs], "reports": reports, "exhaustive": False}, indent=2, default=str))
                    if len(refs) < p.novelty_references:
                        raise ValueError(
                            f"novelty search returned {len(refs)} sources; configured minimum is {p.novelty_references}. Coverage is insufficient, not evidence of novelty."
                        )
                    if sum(bool(e.abstract or e.full_text or e.excerpt) for e in refs) < min(4, p.novelty_references):
                        raise ValueError("novelty requires inspectable paper content, not metadata alone")
                    if not coverage["sufficient_for_assessment"]:
                        raise ValueError("novelty search lacks independent inspectable evidence; see saved coverage report")
                    idea.evidence = [e.id for e in refs]
                    found.update({e.id: e for e in refs})
                s.evidence = list(found.values())
            out = self._judge(
                s,
                agents,
                {
                    "active_seed_ids": [idea.id for idea in pending],
                    "task": "Score the newly proposed candidates against literature and previously accepted seed ideas. Preserve earlier accepted novelty scores; identify whether each adds a distinct novel mechanism.",
                },
            )
            if out.decision == "accept":
                if not {idea.id for idea in pending}.issubset(out.novelty_scores) or not set(
                    out.novelty_scores
                ).issubset({idea.id for idea in s.ideas}):
                    raise ValueError(
                        "novelty checker must score each new candidate without unknown ideas"
                    )
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
                self._stop(s, "seed_pool_exhausted", failed=True)
            else:
                s.stage = Stage.GENERATE_IDEAS
        elif stage == Stage.FILTER_IDEAS:
            active = sorted(
                (idea for idea in s.ideas if idea.status == "seed"),
                key=lambda idea: idea.novelty,
                reverse=True,
            )
            if len(active) < p.initial_candidates:
                raise ValueError("filtering requires enough active seed candidates")
            out = self._judge(s, agents, {"active_seed_ids": [idea.id for idea in active]})
            if out.decision == "accept":
                s.queue = [i.id for i in active[: p.initial_candidates]]
                s.stage = Stage.BASELINE
            elif out.decision == "refine" and s.counters.get("generation", 0) < p.generation_rounds:
                for idea in active:
                    idea.status = "rejected_novelty"
                s.stage = Stage.GENERATE_IDEAS
            else:
                self._stop(s, "novelty_not_verified", failed=True)
        elif stage in {Stage.SUBSET_CRITIC, Stage.FULL_CRITIC}:
            out = self._judge(s, agents)
            current = self._idea(s)
            ref = s.baseline if stage == Stage.SUBSET_CRITIC else c.project.sota
            if out.decision == "accept" and not self._better(current.metrics, ref, c):
                out.decision = "refine"
                s.feedback += "\nMeasured metrics do not establish strict, consistent improvement."
            count_key = "subset_engineering" if stage == Stage.SUBSET_CRITIC else "full_engineering"
            if out.decision == "accept":
                if stage == Stage.SUBSET_CRITIC:
                    current.status, s.stage = "subset_good", Stage.FULL
                else:
                    current.status = "good"
                    self._finish_candidate(s, c)
            elif out.decision == "refine" and s.counters.get(count_key, 0) < p.engineering_rounds:
                s.counters[count_key] = s.counters.get(count_key, 0) + 1
                s.stage = (
                    Stage.SUBSET_ENGINEER if stage == Stage.SUBSET_CRITIC else Stage.FULL_ENGINEER
                )
            else:
                current.status = "bad"
                self._finish_candidate(s, c)
        elif stage == Stage.EVOLVE:
            out = agents.run(s, stage, {"requested_ideas": p.evolved_per_round})
            if out.decision != "accept":
                raise ValueError("evolver proposals did not pass the configured agent panel")
            ids = self._add_ideas(s, out.ideas[: p.evolved_per_round], evolved=True)
            if not ids:
                raise ValueError("evolver returned no distinct hypotheses")
            fresh = [i.id for i in s.ideas if i.status == "seed"][: p.exploration_per_round]
            s.queue = ids + fresh
            self._next_candidate(s)
        elif stage == Stage.SELECT:
            out = self._judge(s, agents)
            good = {i.id for i in s.ideas if i.status == "good"}
            if out.decision != "accept" or out.selected_id not in good:
                raise ValueError(
                    "selector must independently accept a full-benchmark successful candidate"
                )
            s.selected_idea = s.current_idea = out.selected_id
            s.stage = Stage.ABLATION_PLAN
        elif stage in {Stage.ABLATION_PLAN, Stage.REBUTTAL_PLAN}:
            out = agents.run(s, stage)
            if not out.plans or any(
                not isinstance(plan.get("question"), str) for plan in out.plans
            ):
                raise ValueError("planner must return nonempty executable plans with questions")
            s.plans, s.plan_index = out.plans, 0
            s.stage = Stage.ABLATION if stage == Stage.ABLATION_PLAN else Stage.REBUTTAL
        elif stage == Stage.ABLATION_CRITIC:
            out = self._judge(
                s,
                agents,
                {
                    "attribution_requirement": (
                        "ScientistTwo Appendix B rejects gains explained only by generic controls. "
                        "Return structured.attribution with mechanism (nonempty description), "
                        "supported (boolean), generic_controls_only (boolean), rationale (nonempty), "
                        "and experiment_ids citing completed component ablations of this selected idea. "
                        "Accept only when controlled measurements attribute gain to the proposed mechanism."
                    ),
                },
            )
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
                                structured.get("attribution")
                                if isinstance(structured, dict)
                                else None
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
                    cited = (
                        attribution.get("experiment_ids", [])
                        if isinstance(attribution, dict)
                        else []
                    )
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
                            isinstance(identifier, str) and identifier in eligible
                            for identifier in cited
                        )
                    )
                    supported = supported and valid
                s.memory.append(
                    {
                        "kind": "ablation_attribution",
                        "idea": s.selected_idea,
                        "supported": supported,
                        "assessments": assessments,
                    }
                )
                if not supported:
                    out.decision = "refine"
                    s.feedback += "\nAblation evidence does not attribute gain to the proposed mechanism; generic controls alone are insufficient."
            if out.decision == "accept":
                s.stage = Stage.DRAFT
            elif s.counters.get("ablation_refinements", 0) >= p.ablation_rounds:
                self._stop(s, "ablation_gain_not_attributed", failed=True)
            else:
                s.counters["ablation_refinements"] = s.counters.get("ablation_refinements", 0) + 1
                s.stage = Stage.ABLATION_REFINE
        elif stage == Stage.COMPARE:
            if s.candidate_update is None or s.candidate_update.id == s.selected_idea:
                raise ValueError("comparison requires a distinct archived refinement hypothesis")
            out = self._judge(
                s,
                agents,
                {
                    "previous_best": self._idea(s, s.selected_idea).model_dump(),
                    "proposed": s.candidate_update.model_dump() if s.candidate_update else None,
                },
            )
            old = self._idea(s, s.selected_idea)
            improved = (
                s.candidate_update is not None
                and out.decision == "accept"
                and self._better(s.candidate_update.metrics, old.metrics, c)
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
                    "experiment_ids": self._workspace_experiment_ids(s, proposal.workspace),
                }
                s.memory.append(decision)
                self.store.artifact(
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
        elif stage in {Stage.DRAFT, Stage.REVISE}:
            out = agents.run(s, stage)
            if len(out.manuscript.strip()) < 100:
                raise ValueError("writer returned no substantive manuscript")
            s.manuscript = out.manuscript
            self.store.artifact(s.id, "manuscript", f"manuscript-v{s.version}.md", s.manuscript)
            if stage == Stage.REVISE:
                s.counters["peer_revisions"] = s.counters.get("peer_revisions", 0) + 1
            s.stage = Stage.PEER_REVIEW
        elif stage == Stage.PEER_REVIEW:
            # Table 5 reports round 0 before rebuttal and rounds 1/2 after revision.
            # Interpret peer_rounds as revision cycles, separately from initial review.
            out = self._judge(s, agents)
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
            ) >= p.peer_rounds:
                s.stage = Stage.META_REVIEW
            else:
                s.stage = Stage.REBUTTAL_PLAN
        elif stage == Stage.META_REVIEW:
            out = self._judge(s, agents)
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
        elif stage == Stage.INTEGRITY:
            self._final_integrity(s, c, agents)
        elif stage == Stage.COMPLETE:
            s.status = "completed"
        else:
            raise ValueError(f"unimplemented stage: {stage}")

    def _judge(
        self, s: RunState, agents: AgentRunner, context: dict[str, Any] | None = None
    ) -> AgentOutput:
        out = agents.run(s, s.stage, context)
        s.feedback = out.feedback or out.summary
        s.memory.append(
            {
                "kind": "critique",
                "stage": s.stage.value,
                "idea": s.current_idea,
                "decision": out.decision,
                "stage_decision": out.stage_decision,
                "feedback": s.feedback,
                "score": out.score,
                "version": s.version,
            }
        )
        return out

    def _execute_pending(
        self, s: RunState, executor: Executor, spec: ExperimentSpec
    ) -> ExperimentResult:
        """Reconcile execution intent before dispatch; never replay an unknown local run."""
        receipts = self.store.run_dir(s.id) / "receipts"
        receipts.mkdir(exist_ok=True, mode=0o700)
        receipt_name = f"{spec.id}.json"
        started_name = f"{spec.id}.started.json"
        if (receipts / receipt_name).exists():
            result = ExperimentResult.model_validate_json(_read(receipts, receipt_name, 32_000_000))
        elif s.pending_job_id:
            result = executor.poll(spec, s.pending_job_id)
        elif (
            executor.config.backend == "slurm"
            and (Path(spec.workspace) / ".autoresearch-execution.json").exists()
        ):
            # Executor validates the saved specification and recovers the scheduler ID.
            # An uncertain submission remains blocked until its saved job is reconciled.
            result = executor.run(spec)
        elif (receipts / started_name).exists():
            started = json.loads(_read(receipts, started_name, 32_000_000))
            if started["spec"] != spec.model_dump(mode="json"):
                raise ValueError("started execution specification changed before reconciliation")
            result = ExperimentResult(
                id=spec.id,
                status="failed",
                stderr=(
                    "Interrupted experiment has no durable receipt; execution outcome is unknown. "
                    "The workspace and logs are retained. Inspect them before a new attempt; "
                    "this experiment ID will not be replayed."
                ),
                provenance={
                    "uncertain_execution": True,
                    "failure_kind": "interrupted_unknown_outcome",
                    "argv": spec.argv,
                    "started_at": started["started_at"],
                },
            )
        else:
            _write(
                receipts,
                started_name,
                json.dumps(
                    {
                        "spec": spec.model_dump(mode="json"),
                        "started_at": now(),
                    }
                ),
            )
            self.store.event(s.id, "execution_started", s.stage, {"id": spec.id})
            result = executor.run(spec)
        if result.id != spec.id:
            raise ValueError("execution result identifier does not match pending experiment")
        if result.status == "pending":
            if not result.job_id:
                raise ValueError("pending execution did not provide a resumable scheduler job ID")
            s.pending_job_id, s.status = result.job_id, "waiting"
            self.store.save(s, "execution_waiting", {"id": spec.id, "job_id": result.job_id})
        else:
            _write(receipts, receipt_name, result.model_dump_json())
        return result

    def _experiment(self, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
        if len(s.experiments) >= c.budget.max_experiments:
            raise BudgetExceeded("experiment budget reached")
        if (
            c.mode == "live"
            and s.stage == Stage.BASELINE
            and (not c.project.source_dir or not c.project.sota)
        ):
            raise ValueError(
                "live experiments require source_dir and original full-benchmark sota metrics in project config"
            )
        if c.mode == "live" and self.executor is None and not c.project.evaluator_argv:
            raise ValueError(
                "live experiments require an operator-owned protected evaluator; model-generated metrics alone cannot validate research"
            )
        if c.mode == "live" and not all(key in c.project.sota for key in c.project.metrics):
            raise ValueError("original SOTA must specify every required metric")
        executor = self.executor or Executor(c.execution)
        if s.active_output is None:
            context: dict[str, Any] = {
                "source_files": self._source_context(self._source_for(s))
                if c.mode == "demo"
                else {},
                "source_dir": str(self._source_for(s)),
                "current_plan": s.plans[s.plan_index]
                if s.plans and s.stage in {Stage.ABLATION, Stage.REBUTTAL}
                else None,
            }
            s.active_output = agents.run(s, s.stage, context)
            if (
                s.stage in {Stage.ABLATION_REFINE, Stage.META_REFINE}
                and c.mode == "live"
                and (
                    len(s.active_output.ideas) != 1
                    or not s.active_output.ideas[0].hypothesis.strip()
                )
            ):
                s.active_output = None
                raise ValueError(
                    "method refinement requires exactly one revised hypothesis with its implementation"
                )
            self._validate_edits(s.active_output, c)
            if s.stage == Stage.BASELINE and c.project.baseline_argv:
                s.active_output.argv = c.project.baseline_argv
            if not s.active_output.argv:
                raise ValueError("coding agent must propose an executable argv")
        if s.pending_experiment is None:
            seed = c.project.seeds[len(s.batch_results)]
            exp_id = f"exp-{uuid.uuid4().hex[:12]}"
            workspace = self.store.run_dir(s.id) / "experiments" / exp_id
            self._snapshot(
                self._source_for(s),
                workspace,
            )
            self._restore_protected(s.id, workspace, c)
            for edit in s.active_output.files:
                _write(workspace, edit.path, edit.content)
            for relative in s.active_output.deleted_files:
                with _parent(workspace, relative) as (descriptor, name):
                    os.unlink(name, dir_fd=descriptor)
            input_snapshot = self.store.run_dir(s.id) / "inputs" / exp_id
            self._snapshot(workspace, input_snapshot)
            self.store.artifact(
                s.id,
                "code_modifications",
                f"edits-{exp_id}.json",
                json.dumps([edit.model_dump() for edit in s.active_output.files], indent=2),
            )
            s.pending_experiment = ExperimentSpec(
                id=exp_id,
                kind=s.stage,
                workspace=str(workspace),
                argv=s.active_output.argv,
                files=s.active_output.files,
                seed=seed,
                timeout_seconds=c.project.experiment_timeout,
                metadata={
                    "idea_id": s.current_idea,
                    "selected_idea": s.selected_idea,
                    "input_snapshot": str(input_snapshot),
                    "round": s.round,
                    "plan": s.plans[s.plan_index]
                    if s.plans and s.stage in {Stage.ABLATION, Stage.REBUTTAL}
                    else None,
                    "evaluator_argv": c.project.evaluator_argv,
                    "dataset_manifest": c.project.dataset_manifest,
                    "protected_files": self._protected_files(workspace, c),
                    "specification_sha256": hashlib.sha256(
                        c.project.specification.encode()
                    ).hexdigest(),
                },
            )
            self.store.save(
                s,
                "experiment_planned",
                {"id": exp_id, "kind": s.stage.value, "argv": s.active_output.argv, "seed": seed},
            )
        spec = s.pending_experiment
        result = self._execute_pending(s, executor, spec)
        if result.status == "pending":
            return
        result.provenance.update(
            {
                "workspace": spec.workspace,
                "input_snapshot": spec.metadata.get("input_snapshot"),
                "kind": spec.kind,
                "idea_id": s.current_idea,
                "seed": spec.seed,
                "selected_idea": spec.metadata.get("selected_idea"),
                "plan": spec.metadata.get("plan"),
                "specification_sha256": spec.metadata.get("specification_sha256"),
            }
        )
        if result.status == "completed" and not all(
            key in result.metrics for key in c.project.metrics
        ):
            result.status, result.stderr = "failed", "Missing required measured metrics"
        if result.status == "completed":
            audit = agents.run(
                s,
                "experiment_integrity",
                {
                    "experiment": result.model_dump(),
                    "proposed_files": [edit.model_dump() for edit in spec.files],
                    "source_files": self._source_context(Path(spec.workspace)),
                    "specification": c.project.specification,
                },
            )
            self.store.event(
                s.id,
                "experiment_integrity",
                s.stage,
                {"id": result.id, "decision": audit.decision, "feedback": audit.feedback},
            )
            if audit.decision != "accept":
                result.status, result.stderr = (
                    "failed",
                    "Integrity audit: " + (audit.feedback or audit.summary),
                )
        s.experiments.append(result)
        s.batch_results.append(result)
        s.memory.append(
            {
                "kind": "experiment",
                "stage": s.stage.value,
                "idea": s.current_idea,
                "id": result.id,
                "status": result.status,
                "metrics": result.metrics,
                "failure": result.stderr,
                "provenance": result.provenance,
            }
        )
        self.store.event(s.id, "experiment_completed", s.stage, result.model_dump())
        s.pending_experiment, s.pending_job_id = None, None
        if len(s.batch_results) < len(c.project.seeds):
            return
        successful = all(r.status == "completed" for r in s.batch_results)
        metrics = (
            {
                key: sum(r.metrics[key] for r in s.batch_results) / len(s.batch_results)
                for key in c.project.metrics
            }
            if successful
            else {}
        )
        # Seedwise values stay intact; the declared preference rule compares mean metrics.
        workspace = s.batch_results[0].provenance["workspace"]
        proposal = s.active_output
        s.memory.append(
            {
                "kind": "experiment_batch",
                "stage": s.stage.value,
                "idea": s.current_idea,
                "workspace": str(workspace),
                "experiment_ids": [result.id for result in s.batch_results],
                "successful": successful,
            }
        )
        s.active_output = None
        s.batch_results = []
        self._experiment_finished(s, c, successful, metrics, str(workspace), proposal)

    def _experiment_finished(
        self,
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
                {"kind": "baseline_workspace", "workspace": str(self._pristine_input(s, workspace))}
            )
            self._next_candidate(s)
        elif stage in {Stage.SUBSET, Stage.SUBSET_ENGINEER, Stage.FULL, Stage.FULL_ENGINEER}:
            idea = self._idea(s)
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
            previous = self._idea(s, s.selected_idea)
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
                    "experiment_ids": self._workspace_experiment_ids(s, workspace),
                }
            )
            s.stage = Stage.COMPARE

    @staticmethod
    def _workspace_experiment_ids(s: RunState, workspace: str) -> list[str]:
        batch = next(
            (
                item
                for item in reversed(s.memory)
                if item.get("kind") == "experiment_batch" and item.get("workspace") == workspace
            ),
            None,
        )
        if batch is not None:
            return list(batch["experiment_ids"])
        return [
            result.id for result in s.experiments if result.provenance.get("workspace") == workspace
        ]

    def _selected_experiments(
        self, s: RunState, c: ResearchConfig, best: Idea
    ) -> list[ExperimentResult]:
        batch = next(
            (
                item
                for item in reversed(s.memory)
                if item.get("kind") == "experiment_batch"
                and item.get("workspace") == best.workspace
            ),
            None,
        )
        experiments = {result.id: result for result in s.experiments}
        if not batch or not isinstance(batch.get("experiment_ids"), list):
            raise ValueError("selected candidate lacks its complete seed-batch provenance")
        originals = [
            experiments[identifier]
            for identifier in batch["experiment_ids"]
            if identifier in experiments
        ]
        expected_kinds = {"full", "full_engineer", "ablation_refine", "meta_refine"}
        if (
            len(originals) != len(c.project.seeds)
            or [result.provenance.get("seed") for result in originals] != c.project.seeds
            or any(
                result.status != "completed" or result.provenance.get("kind") not in expected_kinds
                for result in originals
            )
        ):
            raise ValueError(
                "selected candidate lacks completed full-benchmark evidence for every configured seed"
            )
        return originals

    def _reproduce_selected(self, s: RunState, c: ResearchConfig, best: Idea) -> bool:
        originals = self._selected_experiments(s, c, best)
        if c.integrity.rerun_supplementary:
            originals.extend(
                result
                for result in s.experiments
                if result.status == "completed"
                and result.provenance.get("kind") in {"ablation", "rebuttal"}
                and result.provenance.get("selected_idea") == best.id
            )
        completed_ids = {
            result.provenance.get("reproduced_from")
            for result in s.experiments
            if result.status == "completed"
            and result.provenance.get("kind") == "reproduction"
            and result.provenance.get("selected_idea") == best.id
        }
        remaining = [result for result in originals if result.id not in completed_ids]
        if not remaining:
            s.counters["reproduced_final"] = len(originals)
            return True
        if len(s.experiments) >= c.budget.max_experiments:
            raise BudgetExceeded("experiment budget reached during independent score reproduction")
        original = remaining[0]
        if s.pending_experiment is not None:
            spec = s.pending_experiment
            if (
                spec.kind != "reproduction"
                or spec.metadata.get("reproduced_from") != original.id
                or spec.metadata.get("selected_idea") != best.id
            ):
                raise ValueError("pending reproduction does not match the selected experiment")
        else:
            argv = original.provenance.get("argv")
            source = original.provenance.get("input_snapshot")
            if not isinstance(argv, list) or not argv or not isinstance(source, str):
                raise ValueError(
                    "selected experiment lacks its pristine pre-execution inputs or command"
                )
            exp_id = f"verify-{uuid.uuid4().hex[:12]}"
            workspace = self.store.run_dir(s.id) / "experiments" / exp_id
            self._snapshot(
                Path(source),
                workspace,
            )
            self._restore_protected(s.id, workspace, c)
            spec = ExperimentSpec(
                id=exp_id,
                kind="reproduction",
                workspace=str(workspace),
                argv=argv,
                seed=int(original.provenance["seed"]),
                timeout_seconds=c.project.experiment_timeout,
                metadata={
                    "evaluator_argv": c.project.evaluator_argv,
                    "dataset_manifest": c.project.dataset_manifest,
                    "protected_files": self._protected_files(workspace, c),
                    "reproduced_from": original.id,
                    "selected_idea": best.id,
                },
            )
            s.pending_experiment = spec
            self.store.save(
                s,
                "reproduction_planned",
                {"id": spec.id, "original_id": original.id, "seed": spec.seed},
            )
        executor = self.executor or Executor(c.execution)
        result = self._execute_pending(s, executor, spec)
        if result.status == "pending":
            return False
        result.provenance.update(
            {
                "workspace": spec.workspace,
                "kind": "reproduction",
                "seed": spec.seed,
                "reproduced_from": original.id,
                "selected_idea": best.id,
            }
        )
        matches = result.status == "completed" and all(
            key in result.metrics
            and math.isclose(
                result.metrics[key], value, rel_tol=c.project.reproduction_tolerance, abs_tol=1e-10
            )
            for key, value in original.metrics.items()
        )
        if not matches and result.status == "completed":
            result.status = "failed"
            result.stderr = (
                "Measured result disagrees with the archived result beyond reproduction tolerance."
            )
        s.experiments.append(result)
        s.memory.append(
            {
                "kind": "score_verification",
                "id": result.id,
                "original_id": original.id,
                "seed": spec.seed,
                "status": result.status,
                "metrics": result.metrics,
                "failure": result.stderr,
                "selected_idea": best.id,
            }
        )
        self.store.event(s.id, "score_verification", s.stage, result.model_dump())
        s.pending_experiment, s.pending_job_id = None, None
        if not matches:
            raise ValueError("selected implementation failed independent rerun tolerance")
        s.counters["reproduced_final"] = len(originals) - len(remaining) + 1
        return len(remaining) == 1

    def _final_integrity(self, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
        best = self._idea(s, s.selected_idea)
        if not s.manuscript or not best.workspace or not best.metrics:
            raise ValueError("finalization requires manuscript, measured best result and code")
        # Every seed in the selected full benchmark must reproduce. Pending work is
        # recovered before allocating a new workspace, and failures remain evidence.
        if not self._reproduce_selected(s, c, best):
            return
        if c.mode == "live":
            source = self._pristine_input(s, best.workspace)
            if c.integrity.require_claim_ledger:
                extracted = agents.run(s, "claim_extraction")
                raw_claims = extracted.structured.get("claims")
                if not isinstance(raw_claims, list):
                    raise ValueError("claim extractor did not return a complete claim ledger")
                claims = [Claim.model_validate(item) for item in raw_claims]
                report = verify_claims(s, claims, source)
                for role in ("claim_coverage", "citation_entailment", "method_alignment"):
                    audit = agents.run(s, role, {"claim_report": report, "selected_source": self._source_context(source)})
                    report[role] = audit.model_dump()
                    if audit.decision != "accept":
                        report["issues"].append(f"{role}: {audit.feedback or audit.summary}")
                report["passed"] = not report["issues"]
                report["coverage_verified"] = report["claim_coverage"]["decision"] == "accept"
                self.store.artifact(s.id, "claim_audit", f"claim-audit-v{s.version}.json", json.dumps(report, indent=2))
                s.memory.append({"kind": "claim_audit", "passed": report["passed"], "issues": report["issues"], "version": s.version})
                if report["issues"]:
                    s.feedback = "Repair unsupported claims or conduct missing experiments: " + "\n".join(report["issues"])
                    s.counters["integrity_repairs"] = s.counters.get("integrity_repairs", 0) + 1
                    if s.counters["integrity_repairs"] > c.integrity.citation_repair_rounds:
                        raise ValueError("claim integrity repair budget exhausted; audit remains unresolved")
                    s.stage = Stage.DRAFT
                    return
            citations = audit_references(s.manuscript, s.evidence, self.literature or Literature(c))
            self.store.event(
                s.id,
                "reference_audit",
                s.stage,
                {"verified": citations.verified, "issues": citations.issues},
            )
            s.memory.append(
                {
                    "kind": "reference_audit",
                    "verified": citations.verified,
                    "issues": citations.issues,
                    "version": s.version,
                }
            )
            if citations.issues:
                s.counters["citation_repairs"] = s.counters.get("citation_repairs", 0) + 1
                if s.counters["citation_repairs"] > c.integrity.citation_repair_rounds:
                    raise ValueError("citation verification repair budget exhausted; inspect reference audit")
                s.feedback = (
                    "Correct the bibliography using independently retrieved evidence: "
                    + "\n".join(citations.issues)
                )
                s.stage = Stage.DRAFT
                return
        out = self._judge(
            s, agents, {"selected_source": self._source_context(Path(best.workspace))}
        )
        if out.decision == "accept":
            if c.mode == "live" and (c.heldout_provider or "heldout_review" in c.role_commands):
                frozen = hashlib.sha256(s.manuscript.encode()).hexdigest()
                heldout = agents.run(s, "heldout_review", {"frozen_manuscript_sha256": frozen, "evaluation_only": True})
                s.reviews.append({"kind": "heldout", "manuscript_sha256": frozen, "review": heldout.model_dump(), "optimization_feedback": False})
                self.store.artifact(s.id, "heldout_review", f"heldout-{frozen[:12]}.json", heldout.model_dump_json(indent=2))
            s.status, s.stage = "completed", Stage.COMPLETE
            s.outcome = s.outcome or "completed_without_simulated_acceptance"
            self.store.artifact(s.id, "final_manuscript", f"final-v{s.version}.md", s.manuscript)
            self.store.artifact(
                s.id,
                "reproducibility",
                f"reproducibility-v{s.version}.json",
                json.dumps(
                    {
                        "selected": best.model_dump(),
                        "experiments": [e.model_dump() for e in s.experiments],
                        "config": c.model_dump(),
                        "attempts": attempt_summary(s),
                        "usage": self.store.usage(s.id),
                    },
                    indent=2,
                ),
            )
        elif out.decision == "refine":
            allowed = {Stage.FULL_ENGINEER, Stage.ABLATION_PLAN, Stage.DRAFT, Stage.PEER_REVIEW}
            target = Stage(out.return_stage or Stage.DRAFT)
            if target not in allowed:
                raise ValueError("integrity verifier returned unsupported repair stage")
            s.stage = target
            s.counters["reproduced_final"] = 0
        else:
            self._stop(s, "integrity_rejected", failed=True)

    def _finish_candidate(self, s: RunState, c: ResearchConfig) -> None:
        idea = self._idea(s)
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
            self._next_candidate(s)
        elif s.round + 1 < c.pipeline.experiment_rounds:
            s.round += 1
            s.stage = Stage.EVOLVE
        elif any(i.status == "good" for i in s.ideas):
            s.stage = Stage.SELECT
        else:
            self._stop(s, "no_successful_full_benchmark_idea", failed=True)

    @staticmethod
    def _next_candidate(s: RunState) -> None:
        if not s.queue:
            raise ValueError("candidate queue is empty")
        s.current_idea = s.queue.pop(0)
        Engine._idea(s).status = "evaluating"
        s.counters["subset_engineering"] = s.counters["full_engineering"] = 0
        s.stage = Stage.SUBSET

    @staticmethod
    def _idea(s: RunState, idea_id: str | None = None) -> Idea:
        key = idea_id or s.current_idea
        for idea in s.ideas:
            if idea.id == key:
                return idea
        raise ValueError("current/selected candidate does not exist")

    def _source_for(self, s: RunState) -> Path:
        if s.stage == Stage.BASELINE:
            return self.store.run_dir(s.id) / "source"
        if s.stage == Stage.SUBSET:
            for item in reversed(s.memory):
                if item["kind"] == "baseline_workspace":
                    return Path(item["workspace"])
        idea = self._idea(
            s,
            s.selected_idea
            if s.stage in {Stage.ABLATION, Stage.ABLATION_REFINE, Stage.REBUTTAL, Stage.META_REFINE}
            else None,
        )
        return (
            self._pristine_input(s, idea.workspace)
            if idea.workspace
            else self.store.run_dir(s.id) / "source"
        )

    @staticmethod
    def _pristine_input(s: RunState, workspace: str) -> Path:
        original = next(
            (e for e in reversed(s.experiments) if e.provenance.get("workspace") == workspace), None
        )
        if original is None or not isinstance(original.provenance.get("input_snapshot"), str):
            raise ValueError(
                "candidate lacks pristine input provenance; do not inherit executed outputs"
            )
        return Path(original.provenance["input_snapshot"])

    @staticmethod
    def _add_ideas(s: RunState, ideas: list[Idea], evolved: bool) -> list[str]:
        ids = {i.id for i in s.ideas}
        added = []
        for idea in ideas:
            if (
                not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", idea.id)
                or idea.id in ids
                or not idea.hypothesis.strip()
            ):
                continue
            if evolved and any(parent not in ids for parent in idea.parents):
                raise ValueError("evolved hypothesis references an unknown parent")
            idea.round, idea.status = s.round, "evolved" if evolved else "seed"
            s.ideas.append(idea)
            added.append(idea.id)
            ids.add(idea.id)
        return added

    @staticmethod
    def _better(metrics: dict[str, float], reference: dict[str, float], c: ResearchConfig) -> bool:
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

    @staticmethod
    def _protected_files(workspace: Path, config: ResearchConfig) -> list[str]:
        return sorted(
            str(path.relative_to(workspace))
            for path in workspace.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and any(
                fnmatch.fnmatch(str(path.relative_to(workspace)), pattern)
                for pattern in config.project.protected_paths
            )
        )

    @staticmethod
    def _validate_edits(output: AgentOutput, c: ResearchConfig) -> None:
        for relative in output.deleted_files:
            if any(fnmatch.fnmatch(relative, pattern) for pattern in c.project.protected_paths):
                raise ValueError("agent tried to delete a protected evaluator or specification")
        for edit in output.files:
            if edit.path in c.project.protected_paths or any(
                fnmatch.fnmatch(edit.path, pattern) for pattern in c.project.protected_paths
            ):
                raise ValueError("agent tried to edit a protected evaluator or specification")
            if len(edit.content.encode()) > 10_000_000:
                raise ValueError("model file edit exceeds size limit")

    @staticmethod
    def _snapshot(source: Path, destination: Path) -> None:
        """Never follow workload-created symlinks back into the host filesystem."""
        if source.is_symlink() or not source.is_dir():
            raise ValueError("snapshot source must be a real directory")
        destination.mkdir(parents=True, mode=0o700)
        ignored = {"metrics.json", "__pycache__"}
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            if any(
                part in ignored or part.startswith(".autoresearch-") or part.endswith(".log")
                for part in relative.parts
            ):
                continue
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or not (
                stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
            ):
                raise ValueError("workload snapshot contains a symlink or special file")
            target = destination / relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(item, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as stream, target.open("xb") as output:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("snapshot contains a special file")
                    shutil.copyfileobj(stream, output)
                os.chmod(target, stat.S_IMODE(info.st_mode) & 0o700)

    def _restore_protected(self, run_id: str, workspace: Path, config: ResearchConfig) -> None:
        source = self.store.run_dir(run_id) / "source"
        for relative in self._protected_files(source, config):
            target = workspace / relative
            if target.is_symlink():
                raise ValueError("protected evaluator path became a symlink")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)

    @staticmethod
    def _source_context(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        total = 0
        for item in sorted(path.rglob("*")):
            if (
                item.is_file()
                and not item.is_symlink()
                and item.suffix in {".py", ".toml", ".md", ".json", ".sh"}
                and not item.name.startswith(".autoresearch")
            ):
                size = item.stat().st_size
                if size > 1_000_000 or total + size > 2_000_000:
                    raise ValueError(
                        "source exceeds prompt context limit; supply a narrower project include list"
                    )
                try:
                    result[str(item.relative_to(path))] = item.read_text()
                except UnicodeDecodeError:
                    continue
                total += size
        return result

    @staticmethod
    def _copy_source(original: Path, target: Path, include: list[str]) -> None:
        for path in original.rglob("*"):
            relative = path.relative_to(original)
            if path.is_symlink() or source_is_excluded(relative):
                continue
            if path.is_file() and any(
                fnmatch.fnmatch(str(relative), pattern) for pattern in include
            ):
                if path.stat().st_size > 5_000_000:
                    raise ValueError("source file exceeds snapshot size limit")
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

    @staticmethod
    def _stop(s: RunState, outcome: str, failed: bool = False) -> None:
        s.status, s.outcome = "failed" if failed else "stopped", outcome
