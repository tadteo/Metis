"""Regression checks bind manuscript literals to immutable executed evidence."""

from pathlib import Path

import pytest

from autoresearch.config import ProjectConfig
from autoresearch.contracts import ExecutionConfig, ExperimentResult, ExperimentSpec, RunState
from autoresearch.execution import Executor
from autoresearch.integrity import Claim, analysis_input, verify_claims


def numerical(
    tmp_path: Path,
    text: str,
    value: float,
    measured: float = 0.51,
    unit: str = "scalar",
    **kwargs: object,
) -> dict:
    result = ExperimentResult(
        id="measured",
        status="completed",
        metrics={"score": measured},
        provenance={"metric_units": {"score": unit}},
    )
    state = RunState(
        id="fixture",
        title="Fixture",
        objective="Bind evidence",
        manuscript=text,
        experiments=[result],
    )
    claim = Claim(
        id="claim",
        kind="numerical",
        text=text,
        value=value,
        metric="score",
        experiment_ids=[result.id],
        **kwargs,
    )
    return verify_claims(state, [claim], tmp_path)


def test_false_text_cannot_hide_behind_correct_ledger_value(tmp_path: Path) -> None:
    report = numerical(tmp_path, "Accuracy is 99.99%.", 0.51, unit="fraction")
    assert not report["passed"]
    assert "literal manuscript" in report["issues"][0]


@pytest.mark.parametrize(
    ("text", "value", "measured", "unit"),
    [
        ("Accuracy is 51.0%.", 51.0, 0.5101, "fraction"),
        ("Accuracy is 51.0 percent.", 51.0, 51.01, "percent"),
        ("Latency is 25.0 ms.", 25.0, 0.025, "seconds"),
        ("Latency is 0.025 seconds.", 0.025, 25, "milliseconds"),
        ("Score is 0.510.", 0.510, 0.5101, "scalar"),
        ("Score is 5.10e-3.", 0.0051, 0.005101, "scalar"),
    ],
)
def test_supported_units_and_display_rounding(
    tmp_path: Path, text: str, value: float, measured: float, unit: str
) -> None:
    assert numerical(tmp_path, text, value, measured, unit)["passed"]


@pytest.mark.parametrize(
    ("text", "value", "measured", "unit", "extra"),
    [
        ("Accuracy is 51%.", 51, 0.51, "scalar", {}),
        ("Accuracy is 51.00%.", 51, 0.515, "fraction", {}),
        ("Score is 0.51000.", 0.51, 0.52, "scalar", {"rounding_tolerance": 0.05}),
        ("Accuracy is 51%.", 51, 51, "percent", {"numeric_span": "51"}),
        ("We used 5 seeds and scored 0.51.", 5, 5, "scalar", {}),
    ],
)
def test_ambiguous_unregistered_or_misleading_numbers_fail(
    tmp_path: Path, text: str, value: float, measured: float, unit: str, extra: dict
) -> None:
    assert not numerical(tmp_path, text, value, measured, unit, **extra)["passed"]


def test_explicit_span_disambiguates_multiple_numbers(tmp_path: Path) -> None:
    assert numerical(tmp_path, "We used 5 seeds and scored 0.51.", 0.51, numeric_span="0.51")[
        "passed"
    ]


def test_aggregations_cannot_repeat_seed_or_mix_units(tmp_path: Path) -> None:
    a = ExperimentResult(
        id="a",
        status="completed",
        metrics={"score": 0.4},
        provenance={"metric_units": {"score": "fraction"}},
    )
    b = a.model_copy(deep=True, update={"id": "b", "metrics": {"score": 0.6}})
    text = "Accuracy is 50.0%."
    state = RunState(
        id="fixture", title="Fixture", objective="Test", manuscript=text, experiments=[a, b]
    )
    claim = Claim(
        id="c",
        kind="numerical",
        text=text,
        value=50,
        metric="score",
        aggregation="mean",
        experiment_ids=["a", "b"],
    )
    assert verify_claims(state, [claim], tmp_path)["passed"]
    claim.experiment_ids = ["a", "b", "b"]
    assert not verify_claims(state, [claim], tmp_path)["passed"]
    claim.experiment_ids = ["a", "b"]
    b.provenance["metric_units"]["score"] = "percent"
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_percentage_point_difference_uses_registered_fraction_units(tmp_path: Path) -> None:
    rows = [
        ExperimentResult(
            id=str(i),
            status="completed",
            metrics={"score": v},
            provenance={"metric_units": {"score": "fraction"}},
        )
        for i, v in enumerate([0.55, 0.51])
    ]
    text = "The improvement is 4.0 percentage points."
    claim = Claim(
        id="c",
        kind="numerical",
        text=text,
        value=4,
        metric="score",
        aggregation="difference",
        experiment_ids=["0", "1"],
    )
    state = RunState(
        id="fixture", title="Fixture", objective="Test", manuscript=text, experiments=rows
    )
    assert verify_claims(state, [claim], tmp_path)["passed"]


EVALUATOR = """import json, os
from pathlib import Path
inputs = json.loads(Path(os.environ["AUTORESEARCH_ANALYSIS_INPUTS"]).read_text())
assert all(item["metrics"]["score"] > 0 for item in inputs)
p = min(1.0, 2 * 0.5 ** len(inputs))
analysis = {"schema_version": 1, "method": "two-sided exact sign test; all observations positive", "metric": "score", "statistic": "p_value", "value": p, "input_experiment_ids": [item["id"] for item in inputs], "input_fingerprints": {item["id"]: item["fingerprint"] for item in inputs}}
Path("analysis.json").write_text(json.dumps(analysis))
Path("metrics.json").write_text(json.dumps({"score": 0.3}))
"""


def execute_analysis(tmp_path: Path, evaluator: str = EVALUATOR) -> tuple[RunState, Claim]:
    inputs = [
        ExperimentResult(id=f"input-{i}", status="completed", metrics={"score": v})
        for i, v in enumerate([0.2, 0.4])
    ]
    (tmp_path / "evaluate.py").write_text(evaluator)
    executor = Executor(ExecutionConfig(backend="local", allow_local=True))
    spec = ExperimentSpec(
        id="analysis-run",
        kind="rebuttal",
        workspace=str(tmp_path),
        argv=["python3", "-c", "pass"],
        metadata={
            "evaluator_argv": ["python3", "evaluate.py"],
            "protected_files": ["evaluate.py"],
            "analysis_artifacts": ["analysis.json"],
            "analysis_inputs": [analysis_input(item) for item in inputs],
        },
    )
    result = executor.run(spec)
    state = RunState(
        id="fixture",
        title="Fixture",
        objective="Test",
        manuscript="The exact sign test gives p = 0.5.",
        experiments=[*inputs, result],
    )
    claim = Claim(
        id="stat",
        kind="statistical",
        text=state.manuscript,
        value=0.5,
        metric="score",
        experiment_ids=[i.id for i in inputs],
        analysis_experiment_id=result.id,
        analysis_artifact="analysis.json",
    )
    return state, claim


def test_real_executed_analysis_binds_literal_inputs_and_artifact(tmp_path: Path) -> None:
    state, claim = execute_analysis(tmp_path)
    assert state.experiments[-1].status == "completed"
    assert verify_claims(state, [claim], tmp_path)["passed"]
    # The negative statistical outcome cannot become a significant claim.
    claim.text = state.manuscript = "The result is significant, p < 0.001."
    claim.value = 0.001
    assert not verify_claims(state, [claim], tmp_path)["passed"]
    assert (
        state.experiments[-1].provenance["statistical_analyses"]["analysis.json"]["analysis"][
            "value"
        ]
        == 0.5
    )


def test_preexisting_artifact_not_written_by_evaluator_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "analysis.json").write_text('{"value": 0.00001}')
    state, claim = execute_analysis(
        tmp_path, 'from pathlib import Path\nPath("metrics.json").write_text(\'{"score": 0.3}\')\n'
    )
    assert state.experiments[-1].status == "completed"
    assert not (tmp_path / "analysis.json").exists()
    assert not verify_claims(state, [claim], tmp_path)["passed"]


@pytest.mark.parametrize(
    "mutation",
    ["file", "input", "failed", "wrong_ids", "wrong_metric", "wrong_statistic", "missing_receipt"],
)
def test_analysis_receipt_rejects_tampering_or_mismatched_claim(
    tmp_path: Path, mutation: str
) -> None:
    state, claim = execute_analysis(tmp_path)
    if mutation == "file":
        (tmp_path / "analysis.json").write_text("{}")
    elif mutation == "input":
        state.experiments[0].metrics["score"] = 0.7
    elif mutation == "failed":
        state.experiments[-1].status = "failed"
    elif mutation == "wrong_ids":
        claim.experiment_ids = [state.experiments[0].id]
    elif mutation == "wrong_metric":
        claim.metric = "accuracy"
    elif mutation == "wrong_statistic":
        claim.statistic = "test_statistic"
    else:
        state.experiments[-1].provenance.clear()
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_unexecuted_arbitrary_file_does_not_certify_significance(tmp_path: Path) -> None:
    (tmp_path / "unrelated.txt").write_text("Existing unrelated prose")
    result = ExperimentResult(id="exp", status="completed", provenance={"workspace": str(tmp_path)})
    text = "The result has p < 0.0001."
    state = RunState(
        id="fixture", title="Fixture", objective="Test", manuscript=text, experiments=[result]
    )
    claim = Claim(
        id="c",
        kind="statistical",
        text=text,
        value=0.0001,
        metric="score",
        experiment_ids=["exp"],
        analysis_experiment_id="exp",
        analysis_artifact="unrelated.txt",
    )
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_registered_analysis_config_rejects_unsafe_or_unknown_targets() -> None:
    with pytest.raises(ValueError, match="registered metrics"):
        ProjectConfig(metric_units={"missing": "fraction"})
    with pytest.raises(ValueError):
        ProjectConfig(analysis_artifacts=["../analysis.json"])
    with pytest.raises(ValueError, match="metrics.json"):
        ProjectConfig(analysis_artifacts=["metrics.json"])


def test_tiny_number_precision_cannot_use_absolute_epsilon_to_hide_error(tmp_path: Path) -> None:
    assert not numerical(tmp_path, "Score is 1.00e-14.", 1e-14, measured=2e-14)["passed"]


def test_analysis_cannot_claim_unmeasured_metric(tmp_path: Path) -> None:
    state, claim = execute_analysis(
        tmp_path, EVALUATOR.replace('"metric": "score"', '"metric": "unmeasured"')
    )
    claim.metric = "unmeasured"
    report = verify_claims(state, [claim], tmp_path)
    assert not report["passed"]
    assert "error" in state.experiments[-1].provenance["statistical_analyses"]["analysis.json"]


def test_analysis_cannot_forge_input_fingerprints(tmp_path: Path) -> None:
    evaluator = EVALUATOR.replace(
        'item["fingerprint"] for item in inputs', '"f" * 64 for item in inputs'
    )
    state, claim = execute_analysis(tmp_path, evaluator)
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_analysis_artifact_symlink_after_execution_fails(tmp_path: Path) -> None:
    state, claim = execute_analysis(tmp_path)
    path = tmp_path / "analysis.json"
    target = tmp_path / "copy.json"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_latex_percentage_matches_official_writer_output(tmp_path: Path) -> None:
    text = r"Our method achieves $51.0\%$ accuracy on the benchmark."
    assert numerical(tmp_path, text, 51.0, 0.5101, "fraction", numeric_span=r"51.0\%")["passed"]


@pytest.mark.parametrize("operator", [r"\leq", r"\geq", r"\le", r"\ge"])
def test_latex_statistical_bound(tmp_path: Path, operator: str) -> None:
    state, claim = execute_analysis(tmp_path)
    claim.text = state.manuscript = rf"The exact test gives $p {operator} 0.5$."
    claim.numeric_span = rf"{operator} 0.5"
    assert verify_claims(state, [claim], tmp_path)["passed"]


def relative_claim(
    tmp_path: Path, baseline: float, aggregation: str, text: str, value: float
) -> dict:
    rows = [
        ExperimentResult(
            id=str(i),
            status="completed",
            metrics={"score": v},
            provenance={"metric_units": {"score": "fraction"}},
        )
        for i, v in enumerate([0.55, baseline])
    ]
    claim = Claim(
        id="c",
        kind="numerical",
        text=text,
        value=value,
        metric="score",
        aggregation=aggregation,
        experiment_ids=["0", "1"],
    )
    state = RunState(
        id="fixture", title="Fixture", objective="Test", manuscript=text, experiments=rows
    )
    return verify_claims(state, [claim], tmp_path)


def test_relative_change_percentage_is_distinct_from_percentage_points(tmp_path: Path) -> None:
    assert relative_claim(tmp_path, 0.5, "relative_change", r"The score increased by 10.0\%.", 10)[
        "passed"
    ]
    assert relative_claim(
        tmp_path, 0.5, "difference", "Accuracy increased by 5.0 percentage points.", 5
    )["passed"]
    assert not relative_claim(tmp_path, 0.5, "difference", "Accuracy increased by 5.0%.", 5)[
        "passed"
    ]


def test_relative_change_rejects_zero_baseline(tmp_path: Path) -> None:
    report = relative_claim(tmp_path, 0, "relative_change", "The score increased by 10.0%.", 10)
    assert not report["passed"]
    assert "zero baseline" in report["issues"][0]
