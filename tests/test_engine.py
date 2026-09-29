from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentRequest, AgentResponse, Stage
from autoresearch.demo import DemoProvider
from autoresearch.engine import Engine
from autoresearch.store import Store


def run_demo(tmp_path: Path, provider: DemoProvider | None = None):
    store = Store(tmp_path / "runtime")
    engine = Engine(store, provider=provider)
    run = engine.create("Integration", "Understand polynomial regression", demo=True)
    result = engine.run(run.id, max_steps=200)
    return store, engine, result


def test_complete_real_experiment_workflow_and_resume(tmp_path: Path):
    store, _, result = run_demo(tmp_path)
    assert result.status == "completed", result.error
    assert result.stage == Stage.COMPLETE
    assert result.outcome == "previous_best_retained_meta_refinement_not_superior"
    assert len(result.experiments) >= 20
    assert all(e.provenance.get("code_sha256") for e in result.experiments)
    assert len([i for i in result.ideas if i.status == "good"]) == 4
    assert any(i.parents for i in result.ideas)
    assert {"subset_engineer", "ablation_refine", "rebuttal", "meta_refine"}.issubset(
        {e.provenance.get("kind") for e in result.experiments}
    )
    assert result.reviews[0]["score"] == 6
    assert result.reviews[1]["score"] == 8
    assert result.counters["reproduced_final"] == 6
    reproduced = {e.provenance.get("reproduced_from") for e in result.experiments if e.provenance.get("kind") == "reproduction"}
    assert all(e.id in reproduced for e in result.experiments if e.provenance.get("kind") in {"ablation", "rebuttal"} and e.status == "completed" and e.provenance.get("selected_idea") == result.selected_idea)
    assert Engine(Store(store.root)).step(result.id).version == result.version


def test_pause_and_resume_at_checkpoint(tmp_path: Path):
    store = Store(tmp_path)
    engine = Engine(store)
    run = engine.create("Pause", "Check persistent pause", demo=True)
    engine.pause(run.id)
    assert engine.step(run.id).status == "paused"
    engine = Engine(Store(tmp_path))
    engine.resume(run.id)
    assert engine.step(run.id).stage == Stage.VERIFY_LIMITATIONS


class RejectExperiments(DemoProvider):
    def complete(self, request: AgentRequest) -> AgentResponse:
        result = super().complete(request)
        if request.role in {"subset_critic", "full_critic"}:
            result.data["decision"] = "reject"
            result.data["feedback"] = "No scientific improvement"
        return result


def test_failed_candidates_feed_all_rounds_and_do_not_create_paper(tmp_path: Path):
    _, _, result = run_demo(tmp_path, RejectExperiments())
    assert result.status == "failed"
    assert result.outcome == "no_successful_full_benchmark_idea"
    assert result.round == 3
    assert len([m for m in result.memory if m["kind"] == "candidate_decision"]) == 8
    assert not result.manuscript


def test_budget_stops_without_false_success(tmp_path: Path):
    config = ResearchConfig()
    config.budget.max_calls = 1
    store = Store(tmp_path)
    engine = Engine(store, config)
    run = engine.create("Budget", "Budget pause", demo=True)
    result = engine.run(run.id)
    assert result.status == "budget_exhausted"
    assert result.stage == Stage.VERIFY_LIMITATIONS
    assert store.usage(run.id)["calls"] == 1


def test_cannot_force_complete_or_edit_protected_evaluator(tmp_path: Path):
    from autoresearch.contracts import AgentOutput, FileEdit

    store = Store(tmp_path)
    engine = Engine(store)
    run = engine.create("Intervention", "Do not bypass evidence", demo=True)
    with pytest.raises(ValueError, match="integrity"):
        engine.intervene(run.id, "force done", "complete")
    config = ResearchConfig()
    config.project.protected_paths = ["evaluate.py"]
    with pytest.raises(ValueError, match="protected"):
        engine._validate_edits(
            AgentOutput(summary="malicious", files=[FileEdit(path="evaluate.py", content="fake")]),
            config,
        )


def test_metric_comparison_is_multi_metric_and_directional():
    config = ResearchConfig()
    config.project.result_preference = "pareto"
    config.project.metrics = {"score": "max", "loss": "min"}
    reference = {"score": 1.0, "loss": 1.0}
    assert Engine._better({"score": 2, "loss": 0.5}, reference, config)
    assert not Engine._better({"score": 2, "loss": 1.5}, reference, config)
    assert not Engine._better(reference, reference, config)
    assert not Engine._better({"score": 2}, reference, config)


def test_generated_snapshot_cannot_follow_host_symlink(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    private = tmp_path / "private.txt"
    private.write_text("private fixture")
    (source / "leak.py").symlink_to(private)
    with pytest.raises(ValueError, match="symlink"):
        Engine._snapshot(source, tmp_path / "copy")
    assert not (tmp_path / "copy" / "leak.py").exists()


def test_protected_evaluator_restored_from_original_between_runs(tmp_path: Path):
    store = Store(tmp_path / "runtime")
    engine = Engine(store)
    state = engine.create("Evaluator", "Preserve canonical evaluator", demo=True)
    config = store.get_config(state.id)
    config.project.protected_paths = ["evaluate.py"]
    original = store.run_dir(state.id) / "source" / "evaluate.py"
    original.write_text("original trusted evaluator")
    work = tmp_path / "work"
    work.mkdir()
    (work / "evaluate.py").write_text("tampered by training program")
    engine._restore_protected(state.id, work, config)
    assert (work / "evaluate.py").read_text() == "original trusted evaluator"


def test_cli_reports_unsuccessful_run_as_nonzero(capsys: pytest.CaptureFixture[str]):
    from autoresearch.cli import _print_run
    from autoresearch.contracts import RunState

    assert (
        _print_run(RunState(id="fixture", title="Failed", objective="Test", status="blocked")) == 2
    )
    assert '"blocked"' in capsys.readouterr().out


def test_supplementary_failure_does_not_advance_as_completed_evidence(tmp_path: Path):
    store = Store(tmp_path)
    engine = Engine(store)
    state = engine.create("Supplement", "Retain missing evidence", demo=True)
    config = store.get_config(state.id)
    state.stage = Stage.REBUTTAL
    state.plans = [{"question": "Required missing control"}]
    for _ in range(config.pipeline.engineering_rounds):
        engine._experiment_finished(state, config, False, {}, "unused")
        assert state.stage == Stage.REBUTTAL
        assert state.plan_index == 0
    with pytest.raises(ValueError, match="unresolved evidence"):
        engine._experiment_finished(state, config, False, {}, "unused")


def test_execution_inputs_are_archived_before_outputs_and_inherited_cleanly(tmp_path: Path):
    from autoresearch.contracts import ExperimentResult, RunState

    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("# Original program")
    pristine = tmp_path / "inputs"
    Engine._snapshot(source, pristine)
    (source / "cached_scores.json").write_text('{"score": 1000}')
    state = RunState(id="fixture", title="Fresh rerun", objective="Avoid stale results")
    state.experiments = [
        ExperimentResult(
            id="exp",
            status="completed",
            provenance={"workspace": str(source), "input_snapshot": str(pristine)},
        )
    ]
    assert Engine._pristine_input(state, str(source)) == pristine
    assert not (pristine / "cached_scores.json").exists()
    replay = tmp_path / "replay"
    Engine._snapshot(Engine._pristine_input(state, str(source)), replay)
    assert (replay / "train.py").exists()
    assert not (replay / "cached_scores.json").exists()
