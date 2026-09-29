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


def audit_fixture(tmp_path: Path) -> tuple[Store, RunState, Path]:
    store = Store(tmp_path / "state")
    state = RunState(
        id="abc123abc123",
        title="Integrity reporting",
        objective="Count actual audits",
        stage=Stage.INTEGRITY,
        status="blocked",
    )
    store.create(state, ResearchConfig())
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "purpose": "regression",
                "tasks": [{"id": "digits"}],
                "quality_ratings": [],
                "runs": [
                    {"task": "digits", "variant": "configured", "run_id": state.id, "error": ""}
                ],
            }
        )
    )
    return store, state, suite


def test_all_failed_integrity_audits_count_once_across_event_memory_and_panel(
    tmp_path: Path,
) -> None:
    store, state, suite = audit_fixture(tmp_path)
    store.event(
        state.id,
        "integrity_panel",
        state.stage,
        {"role": "experiment_integrity", "decision": "refine"},
    )
    store.event(
        state.id,
        "experiment_integrity",
        state.stage,
        {"id": "exp-one", "decision": "refine", "feedback": "protocol violation"},
    )
    reference = {"verified": [], "issues": ["fabricated reference"]}
    claim = {"passed": False, "issues": ["unsupported measured result"]}
    store.event(state.id, "reference_audit", state.stage, reference)
    store.event(state.id, "claim_audit", state.stage, claim)
    store.event(
        state.id,
        "agent_completed",
        state.stage,
        {"role": "integrity", "output": {"decision": "refine"}},
    )
    store.event(
        state.id, "integrity_panel", state.stage, {"role": "integrity", "decision": "refine"}
    )
    state.memory.extend(
        [
            {"kind": "reference_audit", "version": 1, **reference},
            {"kind": "claim_audit", "version": 1, **claim},
            {"kind": "critique", "stage": "integrity", "decision": "refine", "version": 1},
        ]
    )
    store.save(state)
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["integrity_failures"]
    assert summary["detected"] == summary["audits_observed"] == 4
    assert summary["by_kind"]["experiment_integrity"]["failed"] == 1
    assert summary["by_kind"]["reference_audit"]["failed"] == 1
    assert summary["by_kind"]["claim_audit"]["failed"] == 1
    assert summary["by_kind"]["final_integrity"]["failed"] == 1
    assert summary["individual_final_review_failures"] == 1
    assert summary["audit_complete"] is False


def test_repeated_identical_audit_attempts_are_not_collapsed(tmp_path: Path) -> None:
    store, state, suite = audit_fixture(tmp_path)
    claim = {"passed": False, "issues": ["still unsupported"]}
    for version in (1, 2):
        store.event(state.id, "claim_audit", state.stage, claim)
        state.memory.append({"kind": "claim_audit", "version": version, **claim})
    # An actual duplicate of a checkpointed memory record is not a third attempt.
    state.memory.append({"kind": "claim_audit", "version": 2, **claim})
    store.save(state)
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["integrity_failures"]
    assert summary["detected"] == summary["audits_observed"] == 2
    assert all(len(row["sources"]) == 2 for row in summary["audits"])


def test_legacy_memory_audits_and_final_consensus_rejections_remain_observable(
    tmp_path: Path,
) -> None:
    store, state, suite = audit_fixture(tmp_path)
    state.memory.extend(
        [
            {"kind": "claim_audit", "passed": False, "issues": ["unsupported claim"], "version": 1},
            {"kind": "reference_audit", "issues": ["unresolved citation"], "version": 2},
        ]
    )
    store.event(
        state.id, "agent_consensus", state.stage, {"role": "integrity", "decision": "reject"}
    )
    store.save(state)
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["integrity_failures"]
    assert summary["detected"] == summary["audits_observed"] == 3


def test_unadjudicated_final_model_calls_do_not_become_completed_audits(tmp_path: Path) -> None:
    store, state, suite = audit_fixture(tmp_path)
    store.event(
        state.id,
        "agent_completed",
        state.stage,
        {"role": "integrity", "output": {"decision": "reject"}},
    )
    store.event(state.id, "claim_audit", state.stage, {"issues": []})
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["integrity_failures"]
    assert summary["audits_observed"] == 1
    assert summary["audits_unverified"] == 1
    assert summary["individual_final_review_failures"] == 1
    assert not summary["audit_complete"]


def test_literature_cumulative_reports_deduplicate_copies_but_preserve_distinct_attempts(
    tmp_path: Path,
) -> None:
    store, state, suite = audit_fixture(tmp_path)
    failure = {
        "provider": "semantic_scholar",
        "status": "failed",
        "error": "HTTPStatusError",
        "http_status": 429,
    }
    success = {"provider": "arxiv", "status": "completed", "returned": 3}
    first = {
        "query": "same scientific query",
        "retrieved_at": "2026-09-29T10:00:00+00:00",
        "limit": 12,
        "providers": [failure, success],
    }
    second = {**first, "retrieved_at": "2026-09-29T11:00:00+00:00"}
    store.artifact(state.id, "novelty_search", "first.json", json.dumps({"reports": [first]}))
    store.artifact(
        state.id, "novelty_search", "second.json", json.dumps({"reports": [first, second]})
    )
    for failures in ([failure], [failure, failure]):
        store.event(
            state.id,
            "literature_coverage",
            state.stage,
            {"coverage": {"provider_failures": failures}},
        )
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["literature_coverage"]
    assert summary["search_requests_observed"] == 2
    assert summary["provider_attempts_observed"] == 4
    assert summary["search_failures"] == 2
    assert summary["distinct_failure_signatures"] == 1
    assert summary["recall"] is None


def test_coverage_only_failures_remain_visible_without_invented_attempt_count(
    tmp_path: Path,
) -> None:
    store, state, suite = audit_fixture(tmp_path)
    coverage = {"provider_failures": [{"provider": "arxiv", "status": "failed"}]}
    store.event(state.id, "literature_coverage", state.stage, {"coverage": coverage})
    store.event(state.id, "literature_coverage", state.stage, {"coverage": coverage})
    state.memory.append({"kind": "novelty_search", "coverage": coverage})
    store.save(state)
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["literature_coverage"]
    assert summary["search_failures"] is None
    assert summary["provider_attempts_observed"] is None
    assert summary["distinct_failure_signatures"] == 1
    assert summary["coverage_events_observed"] == 2


def test_invalid_raw_final_output_stays_unverified_instead_of_breaking_report(
    tmp_path: Path,
) -> None:
    store, state, suite = audit_fixture(tmp_path)
    # AgentRunner journals provider output before validating/repairing its schema.
    store.event(
        state.id,
        "agent_completed",
        state.stage,
        {"role": "integrity", "output": {"decision": ["not a valid verdict"]}},
    )
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["integrity_failures"]
    assert summary["audits_observed"] == 0
    assert summary["individual_final_reviews_observed"] == 1
    assert summary["individual_final_review_failures"] == 0
    assert summary["audit_complete"] is False


def test_legacy_unidentified_reports_and_corrupt_artifacts_never_invent_zero_failures(
    tmp_path: Path,
) -> None:
    store, state, suite = audit_fixture(tmp_path)
    unidentified = {"query": "prior work", "providers": [{"provider": "arxiv", "status": "failed"}]}
    store.artifact(
        state.id, "novelty_search", "old-first.json", json.dumps({"reports": [unidentified]})
    )
    store.artifact(
        state.id, "novelty_search", "old-second.json", json.dumps({"reports": [unidentified]})
    )
    corrupt = store.artifact(
        state.id, "novelty_search", "corrupt.json", json.dumps({"reports": []})
    )
    (store.run_dir(state.id) / corrupt["path"]).write_text("corrupted")
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["literature_coverage"]
    assert summary["search_failures"] is None
    assert summary["provider_attempts_observed"] is None
    assert summary["unidentified_report_signatures"] == 1
    assert summary["unreadable_search_artifacts"] == [corrupt["id"]]


def test_report_consumes_real_retriever_history_and_excludes_cache_hits_from_api_attempts(
    tmp_path: Path,
) -> None:
    from autoresearch.literature import Literature, ProviderResult, novelty_coverage

    class UnavailableProvider:
        name = "fixture-failed"

        def search(self, query: str, count: int, cutoff: str) -> ProviderResult:
            raise ValueError("provider unavailable")

    class EmptyProvider:
        name = "fixture-completed"

        def search(self, query: str, count: int, cutoff: str) -> ProviderResult:
            return ProviderResult(
                total=0, endpoint="https://example.org/search", raw_response='{"papers":[]}'
            )

    store, state, suite = audit_fixture(tmp_path)
    config = ResearchConfig()
    config.literature.full_text = False
    retriever = Literature(config, providers=[UnavailableProvider(), EmptyProvider()])
    for index, query in enumerate(("first topic", "second topic", "first topic")):
        sources = retriever.search(query, 12)
        store.artifact(
            state.id,
            "novelty_search",
            f"retrieval-{index}.json",
            json.dumps({"queries": [query], "reports": retriever.search_history}),
        )
        store.event(
            state.id,
            "literature_coverage",
            state.stage,
            {"idea": str(index), "coverage": novelty_coverage(sources, retriever.search_history)},
        )
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["literature_coverage"]
    assert summary["search_requests_observed"] == 3
    assert summary["cached_search_requests"] == 1
    assert summary["provider_attempts_observed"] == 4
    assert summary["search_failures"] == 2
    assert summary["unidentified_report_signatures"] == 0
    assert summary["unreadable_search_artifacts"] == []


def test_final_panel_member_records_mirror_raw_outputs_without_inflating_audit_count(
    tmp_path: Path,
) -> None:
    store, state, suite = audit_fixture(tmp_path)
    outputs = [{"decision": "accept"}, {"decision": "reject"}]
    for output in outputs:
        store.event(
            state.id, "agent_completed", state.stage, {"role": "integrity", "output": output}
        )
    store.event(
        state.id,
        "integrity_panel",
        state.stage,
        {"role": "integrity", "decision": "refine", "outputs": outputs},
    )
    state.memory.append(
        {"kind": "critique", "stage": "integrity", "decision": "refine", "version": 1}
    )
    store.save(state)
    summary = report_suite(store, suite)["runs"][0]["dimensions"]["integrity_failures"]
    assert summary["detected"] == summary["audits_observed"] == 1
    assert summary["individual_final_reviews_observed"] == 2
    assert summary["individual_final_review_failures"] == 1
    assert summary["individual_final_reviews_unverified"] == 0


@pytest.mark.parametrize("minimum,expected_status", [(2, "ready"), (3, "blocked")])
def test_two_reference_variant_changes_actual_retrieval_and_coverage_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, minimum: int, expected_status: str
) -> None:
    from autoresearch.contracts import AgentOutput, Evidence, Idea
    from autoresearch.engine import Engine

    config = ResearchConfig.model_validate(variants(ResearchConfig())["configs"]["two-references"])
    config.literature.min_novelty_sources = minimum
    calls = []

    class Retriever:
        search_history = [{"query": "fixture", "providers": []}]

        def behavior_identity(self):
            return {"fixture": "two-independent-sources", "version": 1}

        def search(self, query, count):
            calls.append((query, count))
            return [
                Evidence(
                    id=str(i),
                    title=f"Independent {i}",
                    url=f"https://example.org/{i}",
                    provider="fixture",
                    abstract="Inspectable independent content",
                )
                for i in range(2)
            ]

    store = Store(tmp_path)
    engine = Engine(store, config, literature=Retriever())
    state = engine.create("Fixture", "Exercise retrieval budget")
    state.stage = Stage.NOVELTY
    state.ideas = [
        Idea(id="candidate", title="Candidate", hypothesis="Mechanism", status="pending_novelty")
    ]
    store.save(state)
    monkeypatch.setattr(
        engine, "_judge", lambda *a, **kw: AgentOutput(summary="fixture", decision="reject")
    )
    result = engine.step(state.id)
    assert result.status == expected_status
    assert calls == [("Candidate Mechanism", 2)]
    report = next(a for a in store.artifacts(state.id) if a["kind"] == "novelty_search")
    saved = json.loads((store.run_dir(state.id) / report["path"]).read_text())
    assert saved["queries"] == ["Candidate Mechanism"]


def test_baseline_registration_survives_partial_workspace_copy(tmp_path, monkeypatch):
    import shutil

    pytest.importorskip("sklearn")
    root = tmp_path / "suite"
    prepare_suite(
        root, ResearchConfig(execution=ExecutionConfig(backend="local", allow_local=True))
    )
    copy = shutil.copytree
    failed = []

    def interrupted(source, destination, *args, **kwargs):
        if not failed:
            failed.append(str(destination))
            destination.mkdir()
            (destination / "partial.txt").write_text("retained interrupted setup")
            raise OSError("fixture setup interruption")
        return copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(shutil, "copytree", interrupted)
    report = baseline_suite(root)
    assert report["baseline_attempted"] == 12
    assert report["ready_tasks"] == 1
    assert (Path(failed[0]) / "partial.txt").is_file()
    receipt = json.loads((root / "baseline/digits-subset-0.json").read_text())
    assert receipt["status"] == "failed" and "setup interruption" in receipt["stderr"]
    assert baseline_suite(root)["baseline_attempted"] == 12
    assert len(failed) == 1


def test_suite_runtime_errors_affect_report_and_cli_then_preserve_retry_history(
    tmp_path, monkeypatch, capsys
):
    from autoresearch.cli import main
    from autoresearch.engine import Engine
    from autoresearch.evaluation import run_suite

    root = tmp_path / "suite"
    root.mkdir()
    config = ResearchConfig()
    (root / "config.json").write_text(config.model_dump_json())
    suite = {
        "schema_version": 1,
        "purpose": "fixture",
        "quality_ratings": [],
        "runs": [],
        "tasks": [
            {
                "id": "fixture",
                "baseline_ready": True,
                "config": "config.json",
                "title": "Fixture",
                "objective": "Retain failed call",
            }
        ],
    }
    (root / "suite.json").write_text(json.dumps(suite))
    store = Store(tmp_path / "state")
    monkeypatch.setattr(
        Engine,
        "run",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected provider crash")),
    )
    result = run_suite(store, root)
    assert result["failed_or_blocked_task_variants"] == 1
    assert result["runs"][0]["status"] == "failed_execution"
    assert result["runs"][0]["run_status"] == "ready"
    assert main(["--state-dir", str(tmp_path / "state"), "evaluate", "run", str(root)]) == 2
    capsys.readouterr()
    monkeypatch.setattr(Engine, "run", lambda self, run_id, **kw: self.store.get_run(run_id))
    result = run_suite(store, root)
    assert result["failed_or_blocked_task_variants"] == 0
    assert result["runs"][0]["error"] == ""
    assert len(result["runs"][0]["execution_errors"]) == 2


def test_diabetes_split_uses_raw_data_before_training_only_preprocessing(tmp_path):
    datasets = pytest.importorskip("sklearn.datasets")
    root = tmp_path / "suite"
    prepare_suite(root)
    protocol = json.loads((root / "diabetes/source/protocol.json").read_text())
    saved = json.loads((root / "diabetes/source/train_data.json").read_text())
    assert (
        saved["x"] == datasets.load_diabetes(scaled=False).data[protocol["train_indices"]].tolist()
    )


def test_prepared_tasks_register_their_metric_units_and_outputs(tmp_path: Path) -> None:
    base = ResearchConfig.model_validate(
        {
            "project": {
                "metrics": {"legacy": "max"},
                "primary_metric": "legacy",
                "metric_units": {"legacy": "milliseconds"},
                "analysis_artifacts": ["legacy-analysis.json"],
            }
        }
    )
    suite = prepare_suite(tmp_path, base)
    for task in suite["tasks"]:
        config = ResearchConfig.model_validate_json((tmp_path / task["config"]).read_text())
        assert config.project.metric_units == {
            "score": "fraction" if task["id"] == "digits" else "scalar"
        }
        assert config.project.analysis_artifacts == []


@pytest.mark.parametrize(
    "outcome,numerator",
    [("rejected_refinement", 1), ("good", 2), ("bad", 1), ("pending_comparison", 1)],
)
def test_refinement_attempts_remain_in_improvement_denominator(tmp_path, outcome, numerator):
    from autoresearch.contracts import Idea

    store, state, suite = audit_fixture(tmp_path)
    state.ideas = [
        Idea(id="incumbent", title="Incumbent", hypothesis="Original", status="good"),
        Idea(id="refined", title="Refined", hypothesis="Changed", status=outcome),
        Idea(id="unused", title="Unused", hypothesis="Not evaluated", status="seed"),
    ]
    state.experiments = [
        ExperimentResult(
            id="original-run",
            status="completed",
            metrics={"score": 0.8},
            provenance={"idea_id": "incumbent", "kind": "full"},
        ),
        ExperimentResult(
            id="refinement-run",
            status="completed",
            metrics={"score": 0.9 if outcome == "good" else 0.7},
            provenance={"idea_id": "incumbent", "kind": "ablation_refine"},
        ),
    ]
    state.memory.append(
        {
            "kind": "refinement_proposed",
            "hypothesis": state.ideas[1].model_dump(),
            "experiment_ids": ["refinement-run"],
        }
    )
    state.memory.append(
        {
            "kind": "refinement_proposed",
            "hypothesis": state.ideas[2].model_dump(),
            "experiment_ids": ["not-executed"],
        }
    )
    store.save(state, "fixture")
    rate = report_suite(store, suite)["runs"][0]["dimensions"]["improvement_rate"]
    assert rate["denominator"] == 2
    assert rate["numerator"] == numerator
    assert rate["rate"] == numerator / 2
