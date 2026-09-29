"""Crash recovery and negative research history must survive process restarts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ResearchConfig
from autoresearch.contracts import (
    AgentOutput,
    ExecutionConfig,
    ExperimentResult,
    ExperimentSpec,
    Idea,
    RunState,
    Stage,
)
from autoresearch.engine import Engine
from autoresearch.execution import Executor
from autoresearch.integrity import attempt_summary
from autoresearch.store import Store


class CrashExecutor(Executor):
    def __init__(self, backend: str = "local") -> None:
        super().__init__(ExecutionConfig(backend=backend, allow_local=True))
        self.submitted: list[ExperimentSpec] = []
        self.polled: list[str] = []

    def run(self, spec: ExperimentSpec, *, command_only: bool = False) -> ExperimentResult:
        if (
            self.config.backend == "slurm"
            and (Path(spec.workspace) / ".autoresearch-execution.json").exists()
        ):
            return ExperimentResult(id=spec.id, status="pending", job_id="42")
        self.submitted.append(spec)
        (Path(spec.workspace) / "partial-output.txt").write_text("Execution mutated this workspace")
        if self.config.backend == "slurm":
            (Path(spec.workspace) / ".autoresearch-execution.json").write_text('{"job_id":"42"}')
        raise SystemExit("controller died after launch, before receipt")

    def poll(self, spec: ExperimentSpec, job_id: str) -> ExperimentResult:
        self.polled.append(job_id)
        return ExperimentResult(
            id=spec.id, status="completed", metrics={"score": 0.9}, provenance={"argv": spec.argv}
        )


class Runner(AgentRunner):
    def run(self, state: RunState, role: str, context: dict[str, Any] | None = None) -> AgentOutput:
        if role == "peer_review":
            return AgentOutput(summary="Empirical concerns remain", score=6)
        if role == "rebuttal_plan":
            return AgentOutput(
                summary="Replicate robustness", plans=[{"question": "Does it generalize?"}]
            )
        if role == "revise":
            return AgentOutput(
                summary="Updated with measured supplementary results",
                manuscript="A revised scientific manuscript grounded in actual measured evidence. "
                * 4,
            )
        return AgentOutput(
            summary="Independent criterion checked", argv=["python3", "benchmark.py"]
        )


class SuccessExecutor(Executor):
    def run(self, spec: ExperimentSpec, *, command_only: bool = False) -> ExperimentResult:
        return ExperimentResult(
            id=spec.id, status="completed", metrics={"score": 0.9}, provenance={"argv": spec.argv}
        )


def fixture(
    tmp_path: Path, executor: Executor, peer_rounds: int = 2
) -> tuple[Engine, Store, RunState]:
    store = Store(tmp_path / "state")
    config = ResearchConfig()
    config.pipeline.peer_rounds = peer_rounds
    engine = Engine(store, config, executor=executor, runner_factory=Runner)
    state = engine.create("Crash regression", "Never replay uncertain work", demo=True)
    state.ideas = [
        Idea(id="candidate", title="Candidate", hypothesis="Mechanism", status="evaluating")
    ]
    state.current_idea = state.selected_idea = "candidate"
    state.stage = Stage.SUBSET
    store.save(state)
    return engine, store, state


def test_interrupted_formal_experiment_is_retained_without_dirty_replay(tmp_path: Path) -> None:
    executor = CrashExecutor()
    engine, store, state = fixture(tmp_path, executor)
    with pytest.raises(SystemExit):
        engine.step(state.id)
    pending = store.get_run(state.id).pending_experiment
    assert pending is not None
    assert (store.run_dir(state.id) / "receipts" / f"{pending.id}.started.json").is_file()
    restarted = Engine(store, executor=executor, runner_factory=Runner)
    reconciled = restarted.step(state.id)
    assert len(executor.submitted) == 1
    assert reconciled.pending_experiment is None
    assert len(reconciled.experiments) == 1
    result = reconciled.experiments[0]
    assert result.id == pending.id and result.status == "failed"
    assert result.provenance["uncertain_execution"] is True
    assert result.metrics == {}
    assert (
        Path(pending.workspace) / "partial-output.txt"
    ).read_text() == "Execution mutated this workspace"
    assert any(item.get("id") == result.id and item.get("failure") for item in reconciled.memory)
    assert attempt_summary(reconciled)["experiments_failed"] == 1


def test_completed_receipt_wins_over_interrupted_marker(tmp_path: Path) -> None:
    executor = CrashExecutor()
    engine, store, state = fixture(tmp_path, executor)
    with pytest.raises(SystemExit):
        engine.step(state.id)
    pending = store.get_run(state.id).pending_experiment
    assert pending is not None
    receipt = store.run_dir(state.id) / "receipts" / f"{pending.id}.json"
    receipt.write_text(
        ExperimentResult(
            id=pending.id, status="completed", metrics={"score": 0.9}
        ).model_dump_json()
    )
    restored = Engine(store, executor=executor, runner_factory=Runner).step(state.id)
    assert len(executor.submitted) == 1
    assert restored.experiments[0].status == "completed"
    assert restored.experiments[0].metrics == {"score": 0.9}


def test_scheduler_submission_recovers_job_after_controller_crash(tmp_path: Path) -> None:
    executor = CrashExecutor("slurm")
    engine, store, state = fixture(tmp_path, executor)
    with pytest.raises(SystemExit):
        engine.step(state.id)
    restarted = Engine(store, executor=executor, runner_factory=Runner)
    waiting = restarted.step(state.id)
    assert waiting.status == "waiting" and waiting.pending_job_id == "42"
    restored = restarted.step(state.id)
    assert len(executor.submitted) == 1
    assert executor.polled == ["42"]
    assert restored.experiments[0].status == "completed"


def test_interrupted_reproduction_is_archived_and_next_attempt_gets_pristine_inputs(
    tmp_path: Path,
) -> None:
    executor = CrashExecutor()
    engine, store, state = fixture(tmp_path, executor)
    source = store.run_dir(state.id) / "source"
    best = state.ideas[0]
    best.status, best.workspace, best.metrics = "good", str(source), {"score": 0.9}
    state.stage = Stage.INTEGRITY
    state.manuscript = "Manuscript grounded in measured results. " * 4
    state.experiments = [
        ExperimentResult(
            id=f"original-{seed}",
            status="completed",
            metrics={"score": 0.9},
            provenance={
                "kind": "full",
                "seed": seed,
                "workspace": str(source),
                "input_snapshot": str(source),
                "argv": ["python3", "benchmark.py"],
            },
        )
        for seed in (0, 1)
    ]
    state.memory.append(
        {
            "kind": "experiment_batch",
            "workspace": str(source),
            "experiment_ids": [e.id for e in state.experiments],
        }
    )
    store.save(state)
    with pytest.raises(SystemExit):
        engine.step(state.id)
    pending = store.get_run(state.id).pending_experiment
    assert pending is not None
    restarted = Engine(store, executor=executor, runner_factory=Runner)
    reconciled = restarted.step(state.id)
    assert len(executor.submitted) == 1
    assert reconciled.status == "blocked"
    assert reconciled.pending_experiment is None
    failed = reconciled.experiments[-1]
    assert failed.id == pending.id and failed.status == "failed"
    assert failed.provenance["uncertain_execution"]
    assert failed.provenance["reproduced_from"] == "original-0"
    restarted.resume(state.id)
    with pytest.raises(SystemExit):
        restarted.step(state.id)
    newer = store.get_run(state.id).pending_experiment
    assert newer is not None and newer.id != pending.id and newer.workspace != pending.workspace
    assert not (source / "partial-output.txt").exists()
    assert len(store.get_run(state.id).experiments) == 3


def test_pending_refinement_is_in_attempt_denominator_before_comparison(tmp_path: Path) -> None:
    engine, _, state = fixture(tmp_path, CrashExecutor())
    state.stage = Stage.META_REFINE
    state.ideas[0].status = "good"
    proposal = AgentOutput(
        summary="Changed hypothesis",
        ideas=[Idea(id="new", title="New", hypothesis="Novel mechanism")],
    )
    engine._experiment_finished(
        state, ResearchConfig(), True, {"score": 0.9}, "measured-workspace", proposal
    )
    assert state.candidate_update is not None
    assert state.candidate_update.status == "pending_comparison"
    assert attempt_summary(state)["ideas_attempted"] == 2
    assert attempt_summary(state)["ideas_successful"] == 1
    assert state.memory[-1]["hypothesis"]["parents"] == ["candidate"]


@pytest.mark.parametrize("peer_rounds,cycles", [(2, 1), (3, 2)])
def test_review_limit_preserves_default_and_configurable_complete_rebuttal_cycles(
    tmp_path: Path, peer_rounds: int, cycles: int
) -> None:
    engine, store, state = fixture(
        tmp_path,
        SuccessExecutor(ExecutionConfig(backend="local", allow_local=True)),
        peer_rounds=peer_rounds,
    )
    source = store.run_dir(state.id) / "source"
    state.ideas[0].workspace, state.ideas[0].status = str(source), "good"
    state.experiments = [
        ExperimentResult(
            id="original",
            status="completed",
            provenance={"workspace": str(source), "input_snapshot": str(source)},
        )
    ]
    state.stage = Stage.PEER_REVIEW
    store.save(state)
    for _ in range(20):
        state = engine.step(state.id)
        assert state.status not in {"blocked", "failed"}, state.error
        if state.stage == Stage.META_REVIEW:
            break
    assert state.stage == Stage.META_REVIEW
    assert state.counters["peer_revisions"] == cycles
    assert len(state.reviews) == peer_rounds
    supplementary = [e for e in state.experiments if e.provenance.get("kind") == "rebuttal"]
    assert len(supplementary) == 2 * cycles  # Both configured seeds run in every cycle.
    assert all(e.status == "completed" for e in supplementary)


def test_scientific_tradeoff_requires_complete_metrics_and_independent_acceptance(
    tmp_path: Path,
) -> None:
    config = ResearchConfig()
    config.project.metrics = {"score": "max", "loss": "min"}
    reference = {"score": 1.0, "loss": 1.0}
    assert Engine._better({"score": 2.0, "loss": 1.5}, reference, config)
    assert not Engine._better({"score": 2.0}, reference, config)
    assert not Engine._better({"score": 0.5, "loss": 2.0}, reference, config)
    engine, _, state = fixture(tmp_path, CrashExecutor())
    state.ideas[0].metrics = reference
    state.candidate_update = Idea(
        id="tradeoff",
        title="Tradeoff",
        hypothesis="Improves accuracy at a loss cost",
        metrics={"score": 2.0, "loss": 1.5},
    )
    state.stage, state.comparison_origin = Stage.COMPARE, "meta"

    class RejectingRunner(Runner):
        def run(
            self, state: RunState, role: str, context: dict[str, Any] | None = None
        ) -> AgentOutput:
            return AgentOutput(summary="Loss regression is not justified", decision="reject")

    engine._advance(state, config, RejectingRunner(engine.store, config))
    assert state.selected_idea == "candidate"
    assert state.ideas[-1].status == "rejected_refinement"
    assert state.memory[-1]["critic_decision"] == "reject"


def test_uncertain_scheduler_submission_blocks_without_resubmission(tmp_path: Path) -> None:
    class UncertainScheduler(CrashExecutor):
        def run(self, spec: ExperimentSpec, *, command_only: bool = False) -> ExperimentResult:
            if (Path(spec.workspace) / ".autoresearch-execution.json").exists():
                raise ValueError("Slurm submission outcome is uncertain; reconcile saved job")
            return super().run(spec, command_only=command_only)

    executor = UncertainScheduler("slurm")
    engine, store, state = fixture(tmp_path, executor)
    with pytest.raises(SystemExit):
        engine.step(state.id)
    restored = Engine(store, executor=executor, runner_factory=Runner).step(state.id)
    assert restored.status == "blocked"
    assert restored.pending_experiment is not None
    assert "reconcile saved job" in restored.error
    assert len(executor.submitted) == 1
    assert not restored.experiments
    assert attempt_summary(restored)["experiments_attempted"] == 1


def test_restored_refinement_cannot_replace_incumbent_using_same_id(tmp_path: Path) -> None:
    engine, store, state = fixture(tmp_path, CrashExecutor())
    state.stage = Stage.COMPARE
    state.candidate_update = state.ideas[0].model_copy(
        update={"hypothesis": "Changed under same ID", "metrics": {"score": 2}}
    )
    store.save(state)
    updated = engine.step(state.id)
    assert updated.status == "blocked"
    assert updated.ideas[0].hypothesis == "Mechanism"
    assert "distinct archived" in updated.error


@pytest.mark.parametrize(
    "attributed,generic,cited",
    [
        (False, False, ["component"]),
        (True, True, ["component"]),
        (True, False, ["invented"]),
        (True, False, ["stale-component"]),
    ],
)
def test_ablation_cannot_pass_without_current_mechanism_evidence(
    tmp_path: Path, attributed: bool, generic: bool, cited: list[str]
) -> None:
    engine, _, state = fixture(tmp_path, CrashExecutor())
    state.stage = Stage.ABLATION_CRITIC
    state.counters["ablation_refinements"] = 1
    state.experiments = [
        ExperimentResult(
            id="component",
            status="completed",
            metrics={"score": 0.7},
            provenance={"kind": "ablation", "selected_idea": "candidate"},
        ),
        ExperimentResult(
            id="stale-component",
            status="completed",
            provenance={"kind": "ablation", "selected_idea": "previous"},
        ),
    ]
    config = ResearchConfig()

    class AttributionRunner(Runner):
        def run(
            self, state: RunState, role: str, context: dict[str, Any] | None = None
        ) -> AgentOutput:
            assert "experiment_ids" in self.catalog.prompt("ablation_critic")
            return AgentOutput(
                summary="Check component controls",
                structured={
                    "attribution": {
                        "mechanism": "New component",
                        "supported": attributed,
                        "generic_controls_only": generic,
                        "rationale": "Matched component intervention",
                        "experiment_ids": cited,
                    }
                },
            )

    engine._advance(state, config, AttributionRunner(engine.store, config))
    assert state.status == "failed"
    assert state.stage != Stage.DRAFT
    assert state.outcome == "ablation_gain_not_attributed"
    assert state.memory[-1]["kind"] == "ablation_attribution"
    assert not state.memory[-1]["supported"]


def test_exhausted_ablation_refinement_does_not_silently_approve(tmp_path: Path) -> None:
    engine, _, state = fixture(tmp_path, CrashExecutor())
    state.stage = Stage.ABLATION_CRITIC
    state.counters["ablation_refinements"] = 1
    config = ResearchConfig(mode="demo")

    class RefiningRunner(Runner):
        def run(
            self, state: RunState, role: str, context: dict[str, Any] | None = None
        ) -> AgentOutput:
            return AgentOutput(summary="Generic controls explain gain", decision="refine")

    engine._advance(state, config, RefiningRunner(engine.store, config))
    assert state.status == "failed" and state.stage != Stage.DRAFT


def test_completed_ablation_can_support_explicit_mechanism_acceptance(tmp_path: Path) -> None:
    engine, _, state = fixture(tmp_path, CrashExecutor())
    state.stage = Stage.ABLATION_CRITIC
    state.experiments = [
        ExperimentResult(
            id="component",
            status="completed",
            metrics={"score": 0.7},
            provenance={"kind": "ablation", "selected_idea": "candidate"},
        )
    ]
    config = ResearchConfig()

    class SupportedRunner(Runner):
        def run(
            self, state: RunState, role: str, context: dict[str, Any] | None = None
        ) -> AgentOutput:
            return AgentOutput(
                summary="Matched component intervention",
                structured={
                    "attribution": {
                        "mechanism": "Proposed interaction term",
                        "supported": True,
                        "generic_controls_only": False,
                        "rationale": "Removing the interaction reduces held-out score under fixed controls",
                        "experiment_ids": ["component"],
                    }
                },
            )

    engine._advance(state, config, SupportedRunner(engine.store, config))
    assert state.stage == Stage.DRAFT
    assert state.memory[-1]["supported"]


def test_refinement_history_links_every_producing_seed(tmp_path: Path) -> None:
    engine, store, state = fixture(tmp_path, CrashExecutor())
    state.stage = Stage.META_REFINE
    state.ideas[0].status, state.ideas[0].metrics = "good", {"score": 0.9}
    state.memory.append(
        {
            "kind": "experiment_batch",
            "workspace": "refinement-workspace",
            "experiment_ids": ["experiment-seed-0", "experiment-seed-1"],
        }
    )
    proposal = AgentOutput(
        summary="Changed hypothesis",
        ideas=[Idea(id="new", title="New", hypothesis="Unsuccessful revised mechanism")],
    )
    config = ResearchConfig()
    engine._experiment_finished(
        state, config, True, {"score": 0.7}, "refinement-workspace", proposal
    )
    identifier = state.candidate_update.id if state.candidate_update else ""
    assert state.memory[-1]["experiment_ids"] == ["experiment-seed-0", "experiment-seed-1"]
    engine._advance(state, config, Runner(store, config))
    assert state.memory[-1]["experiment_ids"] == ["experiment-seed-0", "experiment-seed-1"]
    assert sum(idea.id == identifier for idea in state.ideas) == 1
    assert attempt_summary(state)["ideas_attempted"] == 2


@pytest.mark.parametrize(
    "unsupported",
    [{}, {"supported": False, "generic_controls_only": True}, {"experiment_ids": ["unknown"]}],
)
def test_accepting_panel_member_cannot_lose_attribution_objection(
    tmp_path: Path, unsupported: dict[str, Any]
) -> None:
    engine, _, state = fixture(tmp_path, CrashExecutor())
    state.stage = Stage.ABLATION_CRITIC
    state.counters["ablation_refinements"] = 1
    state.experiments = [
        ExperimentResult(
            id="component",
            status="completed",
            metrics={"score": 0.7},
            provenance={"kind": "ablation", "selected_idea": "candidate"},
        )
    ]
    config = ResearchConfig()
    supported = {
        "mechanism": "Interaction",
        "supported": True,
        "generic_controls_only": False,
        "rationale": "Matched intervention",
        "experiment_ids": ["component"],
    }

    class PanelRunner(Runner):
        def run(
            self, state: RunState, role: str, context: dict[str, Any] | None = None
        ) -> AgentOutput:
            return AgentOutput(
                summary="Selected or frontier critic accepts",
                structured={
                    "attribution": supported,
                    "panel_outputs": [
                        {"decision": "accept", "structured": {"attribution": supported}},
                        {"decision": "accept", "structured": {"attribution": unsupported}},
                    ],
                },
            )

    engine._advance(state, config, PanelRunner(engine.store, config))
    assert state.status == "failed" and state.stage != Stage.DRAFT
    assert len(state.memory[-1]["assessments"]) == 3
    assert state.memory[-1]["assessments"][-1] == unsupported
