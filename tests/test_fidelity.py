"""Adverse scientific paths, measured-result replacement and complete seed reruns."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoresearch.config import PipelineConfig, ResearchConfig
from autoresearch.contracts import (
    AgentOutput,
    AgentRequest,
    AgentResponse,
    ExecutionConfig,
    ExperimentResult,
    ExperimentSpec,
    Idea,
    RunState,
    Stage,
)
from autoresearch.demo import DemoProvider
from autoresearch.engine import Engine
from autoresearch.execution import Executor
from autoresearch.store import Store


class RejectingProvider(DemoProvider):
    def __init__(self, decision: str = "reject") -> None:
        self.decision = decision
        self.evolution_context: dict[str, Any] | None = None

    def complete(self, request: AgentRequest) -> AgentResponse:
        response = super().complete(request)
        context = json.loads(request.prompt)
        if request.role == "subset_critic":
            response.data.update(decision=self.decision, feedback="Synthetic scientific rejection.")
        if request.role == "evolve":
            self.evolution_context = context
        return response


def setup_run(
    tmp_path: Path, provider: DemoProvider | None = None
) -> tuple[Engine, Store, RunState]:
    config = ResearchConfig()
    config.pipeline.critics = 1
    config.pipeline.seed_count = 4
    config.pipeline.successful_ideas = 1
    config.pipeline.experiment_rounds = 1
    store = Store(tmp_path / "state")
    engine = Engine(store, config, provider=provider)
    return (
        engine,
        store,
        engine.create("Synthetic fidelity test", "Test evidence handling", demo=True),
    )


def test_published_default_iteration_limits_are_retained() -> None:
    limits = PipelineConfig()
    assert (
        limits.limitation_rounds,
        limits.experiment_rounds,
        limits.successful_ideas,
        limits.engineering_rounds,
        limits.ablation_rounds,
        limits.peer_rounds,
        limits.meta_rounds,
        limits.review_threshold,
    ) == (16, 4, 4, 2, 1, 2, 1, 8)


def test_no_success_stops_and_keeps_scientific_failure_history(tmp_path: Path) -> None:
    engine, _, state = setup_run(tmp_path, RejectingProvider())
    final = engine.run(state.id, max_steps=100)
    assert final.status == "failed"
    assert final.outcome == "no_successful_full_benchmark_idea"
    assert sum(idea.status == "bad" for idea in final.ideas) == 2
    decisions = [entry for entry in final.memory if entry["kind"] == "candidate_decision"]
    assert len(decisions) == 2
    assert all(entry["decision"] == "bad" and entry["feedback"] for entry in decisions)
    assert not any(result.provenance["kind"] == "full" for result in final.experiments)


def test_engineering_exhaustion_prunes_without_promotion(tmp_path: Path) -> None:
    engine, store, state = setup_run(tmp_path, RejectingProvider("refine"))
    final = engine.run(state.id, max_steps=100)
    assert final.status == "failed"
    engineering = [
        event
        for event in store.events(state.id)
        if event["kind"] == "agent_started" and event["payload"]["role"] == "subset_engineer"
    ]
    assert len(engineering) == 4  # Two engineering revisions for each of two candidates.
    assert not any(idea.status == "good" for idea in final.ideas)


def test_evolution_receives_failed_decisions_and_experiment_records(tmp_path: Path) -> None:
    provider = RejectingProvider()
    config = ResearchConfig()
    config.pipeline.critics = 1
    config.pipeline.experiment_rounds = 2
    store = Store(tmp_path / "state")
    engine = Engine(store, config, provider=provider)
    state = engine.create("Evolution fixture", "Preserve negative evidence", demo=True)
    final = engine.run(state.id, max_steps=100)
    assert final.status == "failed"
    assert provider.evolution_context is not None
    memory = provider.evolution_context["state"]["memory"]
    assert (
        sum(item["kind"] == "candidate_decision" and item["decision"] == "bad" for item in memory)
        == 2
    )
    assert any(item["kind"] == "experiment" for item in memory)
    assert len([idea for idea in final.ideas if idea.round == 1]) == 1


def test_rejected_seed_history_cannot_complete_a_new_active_pool(tmp_path: Path) -> None:
    engine, store, state = setup_run(tmp_path)
    state.stage = Stage.GENERATE_IDEAS
    state.ideas = [
        Idea(
            id=f"seed-0-{i}",
            title="Old",
            hypothesis=f"Fit quadratic features with regularization variant 0.{i} and measure held-out error.",
            status="rejected_novelty",
        )
        for i in range(4)
    ]
    store.save(state)
    # Rejected history must not satisfy seed_count; each new hypothesis is checked first.
    updated = engine.step(state.id)
    assert updated.stage == Stage.NOVELTY
    assert sum(idea.status == "pending_novelty" for idea in updated.ideas) == 1
    assert engine.step(state.id).stage == Stage.GENERATE_IDEAS


def test_filter_selects_only_active_seeds_even_if_rejected_ones_rank_higher(tmp_path: Path) -> None:
    engine, store, state = setup_run(tmp_path)
    state.stage = Stage.FILTER_IDEAS
    state.ideas = [
        Idea(
            id="rejected",
            title="Rejected",
            hypothesis="Unsupported",
            status="rejected_novelty",
            novelty=10,
        ),
        Idea(id="active-b", title="B", hypothesis="Mechanism B", novelty=6),
        Idea(id="active-a", title="A", hypothesis="Mechanism A", novelty=8),
    ]
    store.save(state)
    updated = engine.step(state.id)
    assert updated.stage == Stage.BASELINE
    assert updated.queue == ["active-a", "active-b"]
    assert updated.ideas[0].status == "rejected_novelty"


@pytest.mark.parametrize("origin", ["ablation", "meta"])
def test_non_superior_refinement_keeps_incumbent(tmp_path: Path, origin: str) -> None:
    engine, store, state = setup_run(tmp_path)
    incumbent = Idea(
        id="best", title="Best", hypothesis="Original method", status="good", metrics={"score": 0.8}
    )
    state.ideas = [incumbent]
    state.selected_idea = state.current_idea = incumbent.id
    state.candidate_update = incumbent.model_copy(
        update={"id": "replacement", "hypothesis": "Different method"}
    )
    state.stage = Stage.COMPARE
    state.comparison_origin = origin
    store.save(state)
    updated = engine.step(state.id)
    assert updated.selected_idea == "best"
    assert updated.candidate_update is None
    assert len(updated.ideas) == 2
    discarded = next(idea for idea in updated.ideas if idea.id == "replacement")
    assert discarded.status == "rejected_refinement"
    assert discarded.hypothesis == "Different method"
    decision = next(item for item in updated.memory if item["kind"] == "candidate_decision")
    assert decision["hypothesis"] == discarded.model_dump()
    assert decision["previous_best"] == "best"
    assert decision["feedback"]
    assert updated.stage == (Stage.INTEGRITY if origin == "meta" else Stage.ABLATION_CRITIC)
    if origin == "meta":
        assert updated.outcome == "previous_best_retained_meta_refinement_not_superior"


def test_strictly_superior_meta_refinement_restarts_ablations_and_reviews(tmp_path: Path) -> None:
    engine, store, state = setup_run(tmp_path)
    state.ideas = [
        Idea(id="best", title="Best", hypothesis="Old", status="good", metrics={"score": 0.8})
    ]
    state.selected_idea = state.current_idea = "best"
    state.candidate_update = Idea(
        id="new",
        title="New",
        hypothesis="Improved mechanism",
        status="good",
        parents=["best"],
        metrics={"score": 0.9},
    )
    state.counters = {"peer_revisions": 2, "ablation_refinements": 1}
    state.stage, state.comparison_origin = Stage.COMPARE, "meta"
    store.save(state)
    updated = engine.step(state.id)
    assert updated.selected_idea == "new"
    assert updated.stage == Stage.ABLATION_PLAN
    assert updated.counters["peer_revisions"] == 0
    assert updated.counters["ablation_refinements"] == 0
    assert updated.ideas[0].status == "superseded"


def test_refinement_preserves_new_scientific_hypothesis_with_code(tmp_path: Path) -> None:
    engine, _, state = setup_run(tmp_path)
    state.ideas = [Idea(id="old", title="Old", hypothesis="Original", status="good")]
    state.selected_idea = state.current_idea = "old"
    state.stage = Stage.META_REFINE
    proposal = AgentOutput(
        summary="A method change",
        ideas=[
            Idea(
                id="proposal",
                title="New mechanism",
                hypothesis="A revised falsifiable mechanism",
                rationale="Addresses meta-review",
            )
        ],
    )
    engine._experiment_finished(
        state, ResearchConfig(), True, {"score": 0.9}, "new-workspace", proposal
    )
    assert state.candidate_update is not None
    assert state.candidate_update.hypothesis == "A revised falsifiable mechanism"
    assert state.candidate_update.parents == ["old"]
    assert state.ideas[0].hypothesis == "Original"
    assert state.candidate_update.workspace == "new-workspace"


class PendingExecutor(Executor):
    def __init__(self, fail_seed: int | None = None) -> None:
        super().__init__(ExecutionConfig(backend="local", allow_local=True))
        self.submitted: list[ExperimentSpec] = []
        self.polled: list[str] = []
        self.fail_seed = fail_seed

    def run(self, spec: ExperimentSpec) -> ExperimentResult:
        self.submitted.append(spec)
        return ExperimentResult(id=spec.id, status="pending", job_id=f"job-{spec.seed}")

    def poll(self, spec: ExperimentSpec, job_id: str) -> ExperimentResult:
        self.polled.append(job_id)
        value = 0.1 if self.fail_seed == spec.seed else 0.8 + 0.1 * spec.seed
        return ExperimentResult(id=spec.id, status="completed", metrics={"score": value})


def integrity_fixture(tmp_path: Path, executor: Executor) -> tuple[Engine, Store, RunState]:
    engine, store, state = setup_run(tmp_path)
    engine.executor = executor
    state.stage = Stage.INTEGRITY
    state.manuscript = "Synthetic manuscript for seed-level score verification. " * 3
    originals = []
    for seed in (0, 1):
        workspace = store.run_dir(state.id) / "experiments" / f"original-{seed}"
        workspace.mkdir(parents=True)
        (workspace / "experiment.py").write_text("# Synthetic source fixture\n")
        originals.append(
            ExperimentResult(
                id=f"original-{seed}",
                status="completed",
                metrics={"score": 0.8 + 0.1 * seed},
                provenance={
                    "kind": "full",
                    "seed": seed,
                    "workspace": str(workspace),
                    "input_snapshot": str(workspace),
                    "argv": ["python3", "experiment.py"],
                },
            )
        )
    best = Idea(
        id="best",
        title="Best",
        hypothesis="Synthetic",
        status="good",
        metrics={"score": 0.85},
        workspace=originals[0].provenance["workspace"],
    )
    state.ideas, state.experiments = [best], originals
    state.selected_idea = state.current_idea = best.id
    state.memory.append(
        {
            "kind": "experiment_batch",
            "workspace": best.workspace,
            "experiment_ids": [result.id for result in originals],
        }
    )
    store.save(state)
    return engine, store, state


def test_final_reproduction_resumes_without_new_workspace_and_checks_all_seeds(
    tmp_path: Path,
) -> None:
    executor = PendingExecutor()
    engine, store, state = integrity_fixture(tmp_path, executor)
    waiting = engine.step(state.id)
    assert waiting.status == "waiting"
    folders_before = set((store.run_dir(state.id) / "experiments").iterdir())
    # A new engine simulates restarting the orchestrator while a job is pending.
    engine = Engine(store, executor=executor)
    first_done = engine.step(state.id)
    assert first_done.stage == Stage.INTEGRITY
    assert set((store.run_dir(state.id) / "experiments").iterdir()) == folders_before
    assert engine.step(state.id).status == "waiting"
    completed = engine.step(state.id)
    assert completed.status == "completed"
    assert [spec.seed for spec in executor.submitted] == [0, 1]
    reproductions = [
        result
        for result in completed.experiments
        if result.provenance.get("kind") == "reproduction"
    ]
    assert {result.provenance["reproduced_from"] for result in reproductions} == {
        "original-0",
        "original-1",
    }
    assert completed.counters["reproduced_final"] == 2


def test_later_seed_reproduction_failure_is_recorded_and_blocks_completion(tmp_path: Path) -> None:
    engine, _, state = integrity_fixture(tmp_path, PendingExecutor(fail_seed=1))
    for _ in range(4):
        state = engine.step(state.id)
    assert state.status == "blocked"
    assert "rerun tolerance" in state.error
    reproduced = [
        result for result in state.experiments if result.provenance.get("kind") == "reproduction"
    ]
    assert [result.status for result in reproduced] == ["completed", "failed"]
    assert state.pending_experiment is None
    assert state.stage == Stage.INTEGRITY
