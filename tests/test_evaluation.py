"""Real public data smoke tests and honest evaluation-denominator reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import ExecutionConfig, ExperimentResult, RunState, Stage
from autoresearch.evaluation import baseline_suite, prepare_suite, report_suite, variants
from autoresearch.store import Store


def test_real_datasets_are_executed_and_failed_baselines_block_readiness(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    config = ResearchConfig(execution=ExecutionConfig(backend="local", allow_local=True))
    suite = prepare_suite(tmp_path / "suite", config)
    assert {t["id"] for t in suite["tasks"]} == {"digits", "diabetes"}
    report = baseline_suite(tmp_path / "suite")
    assert report["baseline_attempted"] == 12
    assert report["ready_tasks"] == 2
    for task in report["tasks"]:
        assert task["full"]["completed"] == task["subset"]["completed"] == 3
        assert all(0 < score < 1 for score in task["full"]["scores"])
    assert baseline_suite(tmp_path / "suite")["baseline_attempted"] == 12
    receipt = tmp_path / "suite/baseline/digits-full-0.json"
    failed = ExperimentResult(id="digits-full-0", status="failed", stderr="fixture failure")
    receipt.write_text(failed.model_dump_json())
    report = baseline_suite(tmp_path / "suite")
    assert report["ready_tasks"] == 1
    assert report["baseline_attempted"] == 12


def test_attempts_and_quality_unknowns_are_not_dropped_or_invented(tmp_path: Path) -> None:
    root = tmp_path / "suite"
    root.mkdir()
    store = Store(tmp_path / "state")
    state = RunState(
        id="abcdefabcdef",
        title="Failed research",
        objective="Measure all outcomes",
        stage=Stage.FULL,
        status="failed",
    )
    store.create(state, ResearchConfig())
    state.experiments = [
        ExperimentResult(id="failed", status="failed"),
        ExperimentResult(id="complete", status="completed", metrics={"score": 0.2}),
    ]
    store.save(state)
    suite = {
        "schema_version": 1,
        "purpose": "test",
        "tasks": [{"id": "digits"}],
        "quality_ratings": [],
        "runs": [
            {"task": "digits", "variant": "configured", "run_id": state.id, "error": ""},
            {
                "task": "digits",
                "variant": "unavailable",
                "run_id": None,
                "error": "provider not configured",
            },
        ],
    }
    (root / "suite.json").write_text(json.dumps(suite))
    result = report_suite(store, root)
    assert result["attempted_task_variants"] == 2
    assert result["failed_or_blocked_task_variants"] == 2
    assert result["capability_parity"] == "unmeasured"
    dimensions = result["runs"][0]["dimensions"]
    assert dimensions["experiment_correctness"]["rate"] == 0.5
    assert dimensions["coding_success"]["rate"] is None
    assert dimensions["idea_novelty_quality"]["score"] is None
    assert dimensions["reviewer_quality"]["score"] is None
    assert dimensions["literature_coverage"]["recall"] is None
    assert dimensions["cost"]["compute_cost_usd"] is None
    assert (root / "report.json").exists()


def test_variants_have_actual_distinct_configuration_and_no_invented_reference() -> None:
    base = ResearchConfig()
    result = variants(base)
    assert "published-routing" not in result["configs"]
    assert "published-routing" in result["requires_operator_reference"]
    assert result["configs"]["two-references"]["literature"]["max_results"] == 2
    assert result["configs"]["single-critic"]["pipeline"]["critics"] == 1
    assert result["configs"]["no-escalation"]["frontier_provider"] is None
    assert base.pipeline.critics == 2
    reference = ResearchConfig()
    reference.provider.model = "operator-verified-reference-model"
    result = variants(base, reference)
    assert (
        result["configs"]["published-routing"]["provider"]["model"]
        == "operator-verified-reference-model"
    )


def test_prepare_never_overwrites_an_existing_evaluation(tmp_path: Path) -> None:
    (tmp_path / "already").write_text("retained")
    with pytest.raises(ValueError, match="never overwritten"):
        prepare_suite(tmp_path)
    assert (tmp_path / "already").read_text() == "retained"


def test_preference_and_configured_laya_ablations_are_executable() -> None:
    config = ResearchConfig()
    config.laya.enabled = True
    alternatives = variants(config)["configs"]
    assert alternatives["pareto-preference"]["project"]["result_preference"] == "pareto"
    assert (
        alternatives["scientific-preference"]["project"]["result_preference"] == "scientific_critic"
    )
    assert alternatives["laya-enabled"]["laya"]["enabled"] is True
    assert alternatives["laya-disabled"]["laya"]["enabled"] is False
    assert config.laya.enabled is True
