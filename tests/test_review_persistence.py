"""Failed ScholarPeer calls retain private evidence before a final context exists."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, Evidence, RunState, Stage
from autoresearch.literature import Literature
from autoresearch.store import Store


class RecordedLiterature(Literature):
    def search(self, query: str, count: int = 40) -> list[Evidence]:
        self.search_history.append(
            {
                "query": query,
                "cutoff": self.publication_cutoff,
                "retrieved_at": "2024-12-31T00:00:00Z",
                "evidence_ids": ["eligible"],
                "exhaustive": False,
                "providers": [
                    {
                        "provider": "fixture",
                        "status": "completed",
                        "raw_response": {"body": "exact search response"},
                    }
                ],
                "limitations": [],
                "excluded": [
                    {
                        "id": "retrieval-excluded",
                        "reason": "post-cutoff",
                        "raw_source": {"title": "Excluded retrieval record"},
                    }
                ],
            }
        )
        return [
            Evidence(
                id="eligible",
                title="Retrieved eligible result",
                url="https://arxiv.org/abs/2401.00001",
                published_at="2024-01-01",
                abstract="Inspectable evidence",
                provider="fixture",
                retrieval={"raw_source": {"title": "Original evidence record"}},
            ),
            Evidence(
                id="future",
                title="Excluded future result",
                url="https://arxiv.org/abs/2501.00001",
                published_at="2025-01-01",
                provider="fixture",
            ),
        ]


def setup_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[AgentRunner, RunState]:
    config = ResearchConfig()
    config.scholarpeer.publication_cutoff = "2024-12-31"
    store = Store(tmp_path / "private")
    state = RunState(
        id="abcdef123456",
        title="Synthetic review",
        objective="Test persistence",
        stage=Stage.PEER_REVIEW,
    )
    store.create(state, config)
    monkeypatch.setattr("autoresearch.specialists.Literature", RecordedLiterature)
    return AgentRunner(store, config), state


def answer(role: str, context: dict[str, Any]) -> AgentOutput:
    if role.endswith("questions"):
        return AgentOutput(
            summary=role, plans=[{"question": f"Distinct question {i}?"} for i in range(5)]
        )
    return AgentOutput(
        summary=role,
        confidence=1,
        evidence_ids=["eligible"] if role.endswith("answers") else [],
        structured={
            "claims": ["claim"],
            "method": "method",
            "evidence": ["experiment"],
            "references": [{"title": role}],
        },
    )


def snapshots(agents: AgentRunner, state: RunState) -> list[dict[str, Any]]:
    return [
        json.loads((agents.store.run_dir(state.id) / record["path"]).read_text())
        for record in agents.store.artifacts(state.id)
        if record["kind"] == "scholarpeer_checkpoint"
    ]


def test_late_qa_failure_retains_raw_search_exclusions_and_rejected_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents, state = setup_review(tmp_path, monkeypatch)

    def call(
        actual_state: RunState, role: str, context: dict[str, Any], index: int, **kwargs: Any
    ) -> AgentOutput:
        if role == "review_technical_answers":
            return AgentOutput(summary="Unsupported technical answer", evidence_ids=["invented"])
        return answer(role, context)

    monkeypatch.setattr(agents, "_one", call)
    with pytest.raises(ValueError, match="semantic repair budget exhausted"):
        agents.run(state, "peer_review")
    saved = snapshots(agents, state)
    assert saved, "Partial evidence vanished because review_context never returned"
    terminal = saved[-1]
    assert terminal["status"] == "failed"
    assert terminal["error"]["type"] == "ValueError"
    assert (
        terminal["search_reports"][0]["providers"][0]["raw_response"]["body"]
        == "exact search response"
    )
    assert (
        terminal["search_reports"][0]["excluded"][0]["raw_source"]["title"]
        == "Excluded retrieval record"
    )
    assert (
        terminal["review_evidence"][0]["retrieval"]["raw_source"]["title"]
        == "Original evidence record"
    )
    assert terminal["source_quality_exclusions"][0]["evidence"]["id"] == "future"
    rejected = [
        row for row in terminal["individual_outputs"] if row["role"] == "review_technical_answers"
    ]
    assert len(rejected) == agents.config.pipeline.max_agent_repairs + 1
    assert all("unretrieved or excluded" in row["validation_error"] for row in rejected)
    assert (
        len(
            [
                row
                for row in terminal["individual_outputs"]
                if row["role"] == "review_novelty_answers"
            ]
        )
        == 5
    )
    assert not any(
        record["kind"] == "scholarpeer_context" for record in agents.store.artifacts(state.id)
    )


def test_retrieval_exception_preserves_partial_provider_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents, state = setup_review(tmp_path, monkeypatch)

    class InterruptedLiterature(RecordedLiterature):
        def search(self, query: str, count: int = 40) -> list[Evidence]:
            results = super().search(query, count)
            if len(self.search_history) == 2:
                self.search_history[-1]["providers"][0].update(
                    status="failed", error="fixture interrupted"
                )
                raise RuntimeError("retrieval interrupted after receiving partial data")
            return results

    monkeypatch.setattr("autoresearch.specialists.Literature", InterruptedLiterature)
    monkeypatch.setattr(
        agents, "_one", lambda state, role, context, index, **kw: answer(role, context)
    )
    with pytest.raises(RuntimeError, match="retrieval interrupted"):
        agents.run(state, "peer_review")
    terminal = snapshots(agents, state)[-1]
    assert terminal["status"] == "failed"
    assert len(terminal["search_reports"]) == 2
    assert terminal["search_reports"][-1]["providers"][0]["status"] == "failed"
    assert terminal["search_reports"][-1]["providers"][0]["raw_response"]
    assert terminal["review_evidence"][0]["id"] == "eligible"


def test_parallel_specialist_failure_retains_completed_other_specialist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Barrier

    agents, state = setup_review(tmp_path, monkeypatch)
    both_started = Barrier(2)

    def call(
        state: RunState, role: str, context: dict[str, Any], index: int, **kw: Any
    ) -> AgentOutput:
        if role in {"review_historian", "review_baseline_scout"}:
            both_started.wait(timeout=3)
        if role == "review_baseline_scout":
            raise RuntimeError("baseline scout failed")
        return answer(role, context)

    monkeypatch.setattr(agents, "_one", call)
    with pytest.raises(RuntimeError, match="baseline scout"):
        agents.run(state, "peer_review")
    terminal = snapshots(agents, state)[-1]
    assert terminal["status"] == "failed"
    assert any(row["role"] == "review_historian" for row in terminal["individual_outputs"])
    assert terminal["search_reports"] and terminal["review_evidence"]


def test_failed_then_successful_attempt_preserves_every_earlier_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents, state = setup_review(tmp_path, monkeypatch)
    fail = True

    def call(
        state: RunState, role: str, context: dict[str, Any], index: int, **kw: Any
    ) -> AgentOutput:
        if fail and role == "review_technical_answers":
            raise RuntimeError("transient fixture error")
        return answer(role, context)

    monkeypatch.setattr(agents, "_one", call)
    with pytest.raises(RuntimeError, match="transient"):
        agents.run(state, "peer_review")
    originals = {
        record["path"]: (agents.store.run_dir(state.id) / record["path"]).read_bytes()
        for record in agents.store.artifacts(state.id)
    }
    assert originals
    fail = False
    agents.run(state, "peer_review")
    saved = snapshots(agents, state)
    assert any(item["status"] == "failed" for item in saved)
    assert saved[-1]["status"] == "completed"
    for path, content in originals.items():
        assert (agents.store.run_dir(state.id) / path).read_bytes() == content
    records = agents.store.artifacts(state.id)
    assert len({record["path"] for record in records}) == len(records)
    assert any(record["kind"] == "scholarpeer_context" for record in records)
    complete = saved[-1]
    assert len(complete["individual_outputs"]) == 19
    assert (
        len([row for row in complete["individual_outputs"] if row["role"] == "review_expansion"])
        == 3
    )


def test_semantic_repairs_escalate_and_remain_inspectable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.contracts import ProviderConfig

    agents, state = setup_review(tmp_path, monkeypatch)
    agents.config.frontier_provider = ProviderConfig(model="strong-fixture")
    summary_routes = []

    def call(
        state: RunState, role: str, context: dict[str, Any], index: int, **kw: Any
    ) -> AgentOutput:
        if role == "review_summary":
            summary_routes.append(bool(kw.get("frontier")))
            if not kw.get("frontier"):
                return AgentOutput(summary="Missing required structured extraction")
        return answer(role, context)

    monkeypatch.setattr(agents, "_one", call)
    agents.run(state, "peer_review")
    assert summary_routes == [False, False, False, True]
    terminal = snapshots(agents, state)[-1]
    summaries = [
        item for item in terminal["individual_outputs"] if item["role"] == "review_summary"
    ]
    assert all("validation_error" in item for item in summaries[:3])
    assert summaries[-1]["escalated"] and "validation_error" not in summaries[-1]
    assert terminal["status"] == "completed"


def test_model_view_preserves_scientific_records_and_archives_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.review import retrieval_model_view

    agents, state = setup_review(tmp_path, monkeypatch)
    experimental = {
        "record": {"scores": [0.4, 0.6], "raw_source": "measured samples"},
        "raw_response": {"instrument": "unchanged exact observation"},
        "abstract": "Scientific abstract",
        "excerpt": "Scientific abstract",
        "nested": [{"record": "negative result", "raw_source": "sample-2"}],
    }
    assert retrieval_model_view({"experiments": experimental}) == {"experiments": experimental}
    inspected = []

    def call(
        state: RunState, role: str, context: dict[str, Any], index: int, **kw: Any
    ) -> AgentOutput:
        if role == "review_literature":
            assert context["summary"]["structured"]["experiments"] == experimental
            assert "raw_source" not in context["retrieved"][0]["retrieval"]
            assert "raw_response" not in context["search_reports"][0]["providers"][0]
            inspected.append(role)
        result = answer(role, context)
        if role == "review_summary":
            result.structured["experiments"] = experimental
        return result

    monkeypatch.setattr(agents, "_one", call)
    agents.run(state, "peer_review")
    assert inspected == ["review_literature"]
    terminal = snapshots(agents, state)[-1]
    assert terminal["individual_outputs"][0]["output"]["structured"]["experiments"] == experimental
    assert terminal["review_evidence"][0]["retrieval"]["raw_source"]
    assert terminal["search_reports"][0]["providers"][0]["raw_response"]


def test_review_redacts_before_projecting_prompt_and_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents, state = setup_review(tmp_path, monkeypatch)
    secret = "synthetic-display-test-boundary-value"  # noqa: S105 - public privacy fixture
    agents.config.privacy.redact_patterns = [secret]

    class BoundaryLiterature(RecordedLiterature):
        def search(self, query: str, count: int = 40) -> list[Evidence]:
            results = super().search(query, count)
            results[0].title = "A" * 1010 + secret
            results[0].retrieval["venue"] = "V" * 500 + secret
            return results

    captured: list[dict[str, Any]] = []

    def call(
        actual_state: RunState, role: str, context: dict[str, Any], index: int, **kwargs: Any
    ) -> AgentOutput:
        if role != "peer_review":
            captured.append(context)
        return answer(role, context)

    monkeypatch.setattr("autoresearch.specialists.Literature", BoundaryLiterature)
    monkeypatch.setattr(agents, "_one", call)
    agents.run(state, "peer_review")
    assert captured
    projected = [context for context in captured if "published_prompt" in context]
    assert projected
    assert "synthetic-display" not in json.dumps(projected)
    assert secret in json.dumps(snapshots(agents, state)[-1]["review_evidence"])
