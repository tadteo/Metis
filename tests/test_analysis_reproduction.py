"""Engine/executor integration: archived statistical evidence must reproduce too."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, ExperimentResult, Idea, RunState, Stage
from autoresearch.engine import Engine
from autoresearch.integrity import analysis_input
from autoresearch.store import Store


class PlannedRunner(AgentRunner):
    def run(self, state: RunState, role: str, context: dict[str, Any] | None = None) -> AgentOutput:
        return AgentOutput(
            summary="Synthetic protected evaluator fixture", argv=["python3", "train.py"]
        )


def executed_fixture(tmp_path: Path) -> tuple[Engine, Store, RunState, Path]:
    source = tmp_path / "source"
    source.mkdir()
    control = tmp_path / "external-observation.json"
    control.write_text('{"mode":"original"}')
    (source / "train.py").write_text(
        'from pathlib import Path\nPath("model.txt").write_text("synthetic model")\n'
    )
    evaluator = """import json, math, os
from pathlib import Path
inputs = json.loads(Path(os.environ["AUTORESEARCH_ANALYSIS_INPUTS"]).read_text())
values = [item["metrics"]["score"] for item in inputs]
mode = json.loads(Path(CONTROL_PATH).read_text())["mode"]
# An exact sign test over the fixture's positive observations. A mutable external
# observation deliberately perturbs the statistic to test independent detection.
positive = sum(value > 0 for value in values) - int(mode == "changed")
tail = min(positive, len(values) - positive)
p_value = min(1.0, 2 * sum(math.comb(len(values), k) for k in range(tail + 1)) / 2 ** len(values))
analysis = {"method":"two-sided exact sign test", "metric":"score", "statistic":"p_value", "value":p_value, "input_experiment_ids":[item["id"] for item in inputs], "input_fingerprints":{item["id"]:item["fingerprint"] for item in inputs}}
if mode != "missing":
    Path("analysis.json").write_text(json.dumps(analysis, indent=2 if mode == "pretty" else None))
# This independently measured aggregate is invariant to the external perturbation.
Path("metrics.json").write_text(json.dumps({"score":sum(values) / len(values)}))
"""
    (source / "evaluate.py").write_text(evaluator.replace("CONTROL_PATH", repr(str(control))))
    config = ResearchConfig()
    config.execution.backend, config.execution.allow_local = "local", True
    config.project.source_dir = str(source)
    config.project.sota = {"score": 0.1}
    config.project.seeds = [17]
    config.project.metric_units = {"score": "fraction"}
    config.project.analysis_artifacts = ["analysis.json"]
    config.project.evaluator_argv = ["python3", "evaluate.py"]
    config.project.protected_paths = ["evaluate.py"]
    config.project.specification = "Synthetic integration fixture with fixed observed inputs."
    store = Store(tmp_path / "runtime")
    engine = Engine(store, config, runner_factory=PlannedRunner)
    state = engine.create("Executed statistics", "Verify every reported result")
    state.current_idea = state.selected_idea = "candidate"
    state.ideas = [
        Idea(
            id="candidate", title="Candidate", hypothesis="Synthetic aggregate", status="evaluating"
        )
    ]
    state.experiments = [
        ExperimentResult(
            id=f"observation-{index}",
            status="completed",
            metrics={"score": value},
            provenance={"kind": "full", "seed": index},
        )
        for index, value in enumerate([0.2, 0.3, 0.4, 0.5])
    ]
    state.experiments.append(
        ExperimentResult(
            id="failed-observation",
            status="failed",
            metrics={"score": 100.0},
            stderr="Unusable observation retained",
        )
    )
    state.stage = Stage.FULL
    store.save(state)
    state = engine.step(state.id)
    assert state.status == "ready", state.error
    assert state.stage == Stage.FULL_CRITIC
    assert state.experiments[-1].status == "completed", state.experiments[-1].stderr
    return engine, store, state, control


def test_formal_execution_captures_registered_units_and_fingerprinted_completed_inputs(
    tmp_path: Path,
) -> None:
    _, store, state, _ = executed_fixture(tmp_path)
    original = state.experiments[-1]
    expected = [
        analysis_input(result) for result in state.experiments[:-1] if result.status == "completed"
    ]
    started = json.loads(
        (store.run_dir(state.id) / "receipts" / f"{original.id}.started.json").read_text()
    )
    metadata = started["spec"]["metadata"]
    assert metadata["metric_units"] == {"score": "fraction"}
    assert metadata["analysis_artifacts"] == ["analysis.json"]
    assert metadata["analysis_inputs"] == expected
    assert original.provenance["analysis_inputs"] == expected
    assert original.provenance["metric_units"] == {"score": "fraction"}
    receipt = original.provenance["statistical_analyses"]["analysis.json"]
    assert receipt["execution_id"] == original.id
    assert receipt["analysis"]["input_experiment_ids"] == [result["id"] for result in expected]
    assert receipt["analysis"]["value"] == 0.125
    assert len(state.experiments) == 6


def test_reproduction_reuses_original_inputs_and_artifacts_despite_later_observations(
    tmp_path: Path,
) -> None:
    engine, store, state, _ = executed_fixture(tmp_path)
    original = state.experiments[-1].model_copy(deep=True)
    state.experiments.append(
        ExperimentResult(id="later-observation", status="completed", metrics={"score": -100.0})
    )
    config = store.get_config(state.id)
    config.project.analysis_artifacts = ["different-output.json"]
    config.project.metric_units = {"score": "percent"}
    state.stage = Stage.INTEGRITY
    assert engine._reproduce_selected(state, config, state.ideas[0])
    reproduced = state.experiments[-1]
    assert reproduced.status == "completed"
    assert reproduced.provenance["analysis_inputs"] == original.provenance["analysis_inputs"]
    assert reproduced.provenance["analysis_artifacts"] == ["analysis.json"]
    assert reproduced.provenance["metric_units"] == {"score": "fraction"}
    assert (
        reproduced.provenance["statistical_analyses"]["analysis.json"]["analysis"]
        == original.provenance["statistical_analyses"]["analysis.json"]["analysis"]
    )
    assert reproduced.provenance["reproduced_from"] == original.id
    assert reproduced.id != original.id


@pytest.mark.parametrize("mode", ["changed", "missing"])
def test_matching_benchmark_metrics_cannot_hide_changed_or_missing_statistic(
    tmp_path: Path, mode: str
) -> None:
    engine, store, state, control = executed_fixture(tmp_path)
    original = state.experiments[-1].model_copy(deep=True)
    control.write_text(json.dumps({"mode": mode}))
    state.stage = Stage.INTEGRITY
    state.manuscript = "Synthetic manuscript claims p = 0.125 from the archived exact sign test."
    store.save(state)
    blocked = engine.step(state.id)
    assert blocked.status == "blocked"
    assert blocked.stage == Stage.INTEGRITY
    assert blocked.pending_experiment is None
    reproduced = blocked.experiments[-1]
    assert reproduced.status == "failed"
    assert reproduced.metrics == original.metrics
    assert "statistical analysis" in reproduced.stderr
    assert reproduced.provenance["reproduced_from"] == original.id
    if mode == "changed":
        assert (
            reproduced.provenance["statistical_analyses"]["analysis.json"]["analysis"]["value"]
            == 0.625
        )
    else:
        assert "error" in reproduced.provenance["statistical_analyses"]["analysis.json"]
    assert any(
        result.id == original.id and result.status == "completed" for result in blocked.experiments
    )
    assert blocked.memory[-1]["kind"] == "score_verification"
    assert blocked.memory[-1]["status"] == "failed"


def test_equivalent_statistical_json_reproduces_despite_new_receipt_and_formatting(
    tmp_path: Path,
) -> None:
    engine, store, state, control = executed_fixture(tmp_path)
    original = state.experiments[-1].model_copy(deep=True)
    control.write_text('{"mode":"pretty"}')
    assert engine._reproduce_selected(state, store.get_config(state.id), state.ideas[0])
    reproduced = state.experiments[-1]
    expected_receipt = original.provenance["statistical_analyses"]["analysis.json"]
    actual_receipt = reproduced.provenance["statistical_analyses"]["analysis.json"]
    assert expected_receipt["execution_id"] != actual_receipt["execution_id"]
    assert expected_receipt["sha256"] != actual_receipt["sha256"]
    assert expected_receipt["analysis"] == actual_receipt["analysis"]
    assert reproduced.status == "completed"
