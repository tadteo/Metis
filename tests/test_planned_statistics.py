"""Inherited paired-test safeguards integrated with real protected-evaluator receipts."""

import json
from pathlib import Path

import pytest

from autoresearch.contracts import ExecutionConfig, ExperimentResult, ExperimentSpec, RunState
from autoresearch.execution import Executor
from autoresearch.integrity import Claim, analysis_input, verify_claims

EVALUATOR = """import itertools, json, os
from pathlib import Path
inputs = json.loads(Path(os.environ["AUTORESEARCH_ANALYSIS_INPUTS"]).read_text())
plan = json.loads(Path(os.environ.get("AUTORESEARCH_STATISTICAL_PLAN", "statistical_plan.json")).read_text())
rows = {item["id"]: item for item in inputs}
ids = [pair[side] for pair in plan["pairs"] for side in ("left", "right")]
diffs = [rows[p["left"]]["metrics"][plan["metric"]] - rows[p["right"]]["metrics"][plan["metric"]] for p in plan["pairs"]]
observed = sum(diffs)
dist = [sum(d*s for d,s in zip(diffs, signs)) for signs in itertools.product((-1,1), repeat=len(diffs))]
if plan["alternative"] == "two-sided":
    count = sum(abs(v) >= abs(observed)-1e-12 for v in dist)
elif plan["alternative"] == "greater":
    count = sum(v >= observed-1e-12 for v in dist)
else:
    count = sum(v <= observed+1e-12 for v in dist)
analysis = {"schema_version":1, "method":"paired_sign_flip", "metric":plan["metric"], "statistic":"p_value", "value":min(1,count/len(dist)*plan["family_size"]), "input_experiment_ids":ids, "input_fingerprints":{i:rows[i]["fingerprint"] for i in ids}}
PATCH
Path("analysis.json").write_text(json.dumps(analysis))
Path("metrics.json").write_text(json.dumps({"score":0.875}))
"""


def execute(
    tmp_path: Path,
    *,
    plan_changes=None,
    mutate=None,
    patch="",
    late_plan=False,
    method="paired_sign_flip",
):
    pairs = [{"left": f"left-{i}", "right": f"right-{i}"} for i in range(6)]
    plan = {
        "schema_version": 1,
        "test": "paired_sign_flip",
        "metric": "score",
        "pairs": pairs,
        "alternative": "two-sided",
        "alpha": 0.05,
        "family_size": 1,
        "correction": "bonferroni",
        "assumptions": "Independent paired units and exchangeable signs under the null; review required.",
        **(plan_changes or {}),
    }
    samples = [
        ExperimentResult(
            id=pair[side],
            status="completed",
            metrics={"score": value},
            provenance={
                "seed": seed,
                "specification_sha256": "a" * 64,
                "code_sha256": ("b" if side == "left" else "c") * 64,
                "data_provenance": {"operator_manifest": {"dataset": "synthetic matched fixture"}},
                "metric_units": {"score": "fraction"},
            },
        )
        for seed, pair in enumerate(pairs)
        for side, value in (("left", 0.875), ("right", 0.75))
    ]
    if mutate:
        mutate(samples)
    content = json.dumps(plan)
    if not late_plan:
        (tmp_path / "statistical_plan.json").write_text(content)
    training = (
        "from pathlib import Path; Path('statistical_plan.json').write_text(" + repr(content) + ")"
        if late_plan
        else "pass"
    )
    (tmp_path / "evaluate.py").write_text(
        EVALUATOR.replace("PATCH", patch + f'\nanalysis["method"]={method!r}')
    )
    spec = ExperimentSpec(
        id="analysis-run",
        kind="rebuttal",
        workspace=str(tmp_path),
        argv=["python3", "-c", training],
        metadata={
            "evaluator_argv": ["python3", "evaluate.py"],
            "protected_files": ["evaluate.py"],
            "analysis_artifacts": ["analysis.json"],
            "analysis_inputs": [analysis_input(x) for x in samples],
        },
    )
    result = Executor(ExecutionConfig(backend="local", allow_local=True)).run(spec)
    state = RunState(
        id="stats",
        title="Synthetic method validation",
        objective="Verify",
        experiments=[*samples, result],
        manuscript="Statistically significant (p = 0.03125).",
    )
    claim = Claim(
        id="stat",
        kind="statistical",
        text=state.manuscript,
        experiment_ids=[x.id for x in samples],
        analysis_experiment_id=result.id,
        analysis_artifact="analysis.json",
        metric="score",
        value=0.03125,
        statistical_conclusion="significant",
    )
    return state, claim, spec


def test_actual_registered_analysis_preserves_generic_receipt_and_method_evidence(tmp_path):
    state, claim, _ = execute(tmp_path)
    result = state.experiments[-1]
    assert result.status == "completed", result.stderr
    receipt = result.provenance["statistical_analyses"]["analysis.json"]
    assert receipt["analysis"]["input_fingerprints"]
    validation = receipt["method_validation"]
    assert validation["validated"]
    assert validation["p_value"] == 0.03125
    assert validation["mean_difference"] == 0.125
    assert validation["assumptions_host_certified"] is False
    assert validation["complete_test_family_host_certified"] is False
    assert validation["registered_before_observing_results"] is False
    assert verify_claims(state, [claim], tmp_path)["passed"]


@pytest.mark.parametrize(
    "alternative,family,p",
    [("two-sided", 1, 2 / 64), ("greater", 1, 1 / 64), ("less", 1, 1.0), ("two-sided", 2, 4 / 64)],
)
def test_exact_tail_and_multiplicity_control_conclusion(tmp_path, alternative, family, p):
    state, claim, _ = execute(
        tmp_path, plan_changes={"alternative": alternative, "family_size": family}
    )
    result = state.experiments[-1]
    assert result.status == "completed", result.stderr
    claim.statistical_conclusion = "significant" if p < 0.05 else "not_significant"
    claim.value = p
    state.manuscript = claim.text = (
        f"{'Statistically significant' if p < 0.05 else 'Not statistically significant'} (p = {p})."
    )
    assert verify_claims(state, [claim], tmp_path)["passed"]
    claim.statistical_conclusion = "not_significant" if p < 0.05 else "significant"
    assert not verify_claims(state, [claim], tmp_path)["passed"]


@pytest.mark.parametrize(
    "mutation", ["duplicate_seed", "protocol", "data", "source", "mixed_source", "units"]
)
def test_invalid_paired_provenance_fails_execution_and_retains_receipt(tmp_path, mutation):
    def mutate(samples):
        if mutation == "duplicate_seed":
            samples[2].provenance["seed"] = samples[3].provenance["seed"] = 0
        elif mutation == "protocol":
            samples[0].provenance["specification_sha256"] = "different protocol"
        elif mutation == "data":
            samples[0].provenance["data_provenance"] = {}
        elif mutation == "source":
            samples[0].provenance.pop("code_sha256")
        elif mutation == "mixed_source":
            samples[0].provenance["code_sha256"] = "d" * 64
        else:
            samples[0].provenance["metric_units"] = {"score": "percent"}

    state, claim, _ = execute(tmp_path, mutate=mutate)
    result = state.experiments[-1]
    assert result.status == "failed"
    assert result.metrics == {"score": 0.875}
    assert "error" in result.provenance["statistical_analyses"]["analysis.json"]
    assert not verify_claims(state, [claim], tmp_path)["passed"]


@pytest.mark.parametrize(
    "patch",
    [
        'analysis["value"] = 0.001',
        'analysis.update(statistic="effect_size", value=0.5)',
        'analysis["input_experiment_ids"].pop()',
    ],
)
def test_invented_statistical_arithmetic_or_omitted_input_fails(tmp_path, patch):
    state, claim, _ = execute(tmp_path, patch=patch)
    assert state.experiments[-1].status == "failed"
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_plan_created_during_training_is_not_registration(tmp_path):
    state, claim, _ = execute(tmp_path, late_plan=True)
    result = state.experiments[-1]
    assert result.status == "failed"
    assert result.provenance["registered_statistical_plan"] is None
    assert "registered before execution" in result.stderr
    assert not verify_claims(state, [claim], tmp_path)["passed"]


@pytest.mark.parametrize(
    "printed,conclusion,value,valid",
    [
        ("Statistically significant.", "significant", None, True),
        ("Statistically significant.", "estimate", None, False),
        ("Not statistically significant.", "significant", None, False),
        ("No significant difference.", "significant", None, False),
        ("Nonsignificant result.", "significant", None, False),
        ("Statistically insignificant.", "significant", None, False),
        ("Statistically significant (p = 0.000001).", "significant", 0.000001, False),
        ("Statistically significant (p < 0.05).", "significant", 0.05, True),
        (r"Statistically significant (p \leq 0.05).", "significant", 0.05, True),
        ("Statistically significant (p < 0.01).", "significant", 0.01, False),
        ("Statistically significant with 99 controls.", "significant", 99, False),
    ],
)
def test_inherited_significance_and_literal_wording_remain_truthful(
    tmp_path, printed, conclusion, value, valid
):
    state, claim, _ = execute(tmp_path)
    state.manuscript = claim.text = printed
    claim.value, claim.statistical_conclusion = value, conclusion
    assert verify_claims(state, [claim], tmp_path)["passed"] is valid


def test_unknown_method_retains_executed_value_but_cannot_certify_significance(tmp_path):
    state, claim, _ = execute(tmp_path, method="Other declared procedure")
    assert state.experiments[-1].status == "completed"
    state.manuscript = claim.text = "The procedure reports p = 0.03125."
    claim.statistical_conclusion = "estimate"
    assert verify_claims(state, [claim], tmp_path)["passed"]
    state.manuscript = claim.text = "Statistically significant (p = 0.03125)."
    claim.statistical_conclusion = "significant"
    report = verify_claims(state, [claim], tmp_path)
    assert not report["passed"]
    assert "method-specific" in str(report["issues"])


def test_changed_sample_invalidates_fingerprints_before_method_arithmetic(tmp_path):
    state, claim, _ = execute(tmp_path)
    state.experiments[0].metrics["score"] = 0.99
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_reproduction_rejects_changed_plan_even_with_same_data_and_command(tmp_path):
    state, _, spec = execute(tmp_path)
    original = state.experiments[-1]
    plan = json.loads((tmp_path / "statistical_plan.json").read_text())
    plan["family_size"] = 2
    (tmp_path / "statistical_plan.json").write_text(json.dumps(plan))
    spec.metadata["registered_statistical_plan"] = original.provenance[
        "registered_statistical_plan"
    ]
    with pytest.raises(ValueError, match="statistical plan differs"):
        Executor(ExecutionConfig(backend="local", allow_local=True)).run(spec)


def test_valid_effect_estimate_uses_the_same_registered_method_and_inputs(tmp_path):
    state, claim, _ = execute(
        tmp_path, patch='analysis.update(statistic="effect_size", value=sum(diffs)/len(diffs))'
    )
    state.manuscript = claim.text = "Mean difference = 0.125."
    claim.value, claim.statistic, claim.statistical_conclusion = 0.125, "effect_size", "estimate"
    assert verify_claims(state, [claim], tmp_path)["passed"]


@pytest.mark.parametrize("number", ["1e999999999", "1e9999999999999999999", "1e-999999999", "1e-324", "-1e-324"])
def test_inherited_extreme_literal_guard_preserves_safe_numeric_span_binding(tmp_path, number):
    state = RunState(
        id="number",
        title="Test",
        objective="Verify",
        manuscript=f"Score is {number}.",
        experiments=[ExperimentResult(id="e", status="completed", metrics={"score": 0.0})],
    )
    claim = Claim(
        id="c",
        kind="numerical",
        text=state.manuscript,
        experiment_ids=["e"],
        metric="score",
        value=0.0,
    )
    assert not verify_claims(state, [claim], tmp_path)["passed"]


def test_registered_plan_bytes_cannot_be_replaced_by_later_workspace_plan(tmp_path):
    from autoresearch.planned_statistics import register_plan

    state, claim, spec = execute(tmp_path)
    result = state.experiments[-1]
    original = result.provenance["registered_statistical_plan"]
    assert register_plan(tmp_path) == original
    replacement = json.loads(original["content"])
    replacement["family_size"] = 100
    (tmp_path / "statistical_plan.json").write_text(json.dumps(replacement))
    # Verification relies on the execution-owned registration, not the mutable working copy.
    assert verify_claims(state, [claim], tmp_path)["passed"]
    result.provenance["registered_statistical_plan"]["content"] = json.dumps(replacement)
    assert not verify_claims(state, [claim], tmp_path)["passed"]
