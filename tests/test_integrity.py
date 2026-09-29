from pathlib import Path

import pytest

from autoresearch.contracts import AgentOutput, ExperimentResult, RunState
from autoresearch.decisions import normalize_decision
from autoresearch.engine import Engine
from autoresearch.integrity import Claim, attempt_summary, verify_claims
from autoresearch.store import Store


def state() -> RunState:
    return RunState(id="test", title="Measured", objective="Verify", manuscript="Accuracy is 0.81. Statistically significant.", experiments=[ExperimentResult(id="e1", status="completed", metrics={"accuracy": .8}), ExperimentResult(id="e2", status="completed", metrics={"accuracy": .82}), ExperimentResult(id="bad", status="failed", metrics={"accuracy": .99})])


def test_mean_claim_checks_all_producing_results(tmp_path: Path) -> None:
    claim = Claim(id="c1", kind="numerical", text="Accuracy is 0.81.", experiment_ids=["e1", "e2"], metric="accuracy", value=.81, aggregation="mean")
    assert verify_claims(state(), [claim], tmp_path)["passed"]
    claim.value = .91
    assert not verify_claims(state(), [claim], tmp_path)["passed"]
    claim.value = .99
    claim.experiment_ids = ["bad"]
    claim.aggregation = "individual"
    assert not verify_claims(state(), [claim], tmp_path)["passed"]


def test_repeated_seeds_do_not_prove_significance(tmp_path: Path) -> None:
    claim = Claim(id="sig", kind="statistical", text="Statistically significant.", experiment_ids=["e1", "e2"])
    report = verify_claims(state(), [claim], tmp_path)
    assert not report["passed"]
    assert "executed statistical analysis" in str(report["issues"])
    assert attempt_summary(state())["experiments_attempted"] == 3


def test_published_critic_vocabulary_is_preserved() -> None:
    result = normalize_decision("subset_critic", AgentOutput(summary="Tune", stage_decision="Engineer"))
    assert (result.decision, result.stage_decision) == ("refine", "engineer")
    with pytest.raises(ValueError):
        normalize_decision("ablation_critic", AgentOutput(summary="Wrong role", stage_decision="engineer"))


def test_artifacts_are_immutable_and_binary_safe(tmp_path: Path) -> None:
    store = Store(tmp_path)
    run = Engine(store).create("Evidence", "Immutable", demo=True)
    first = store.artifact(run.id, "draft", "paper.tex", "original")
    second = store.artifact(run.id, "draft", "paper.tex", "revised")
    assert first["path"] != second["path"]
    assert (store.run_dir(run.id) / first["path"]).read_text() == "original"
    pdf = store.artifact_bytes(run.id, "pdf", "paper.pdf", b"%PDF-1.7\n\xff")
    assert (store.run_dir(run.id) / pdf["path"]).read_bytes() == b"%PDF-1.7\n\xff"
