"""Pinned retrieval extensions reach real ScholarPeer calls and survive resumption."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoresearch import behavior
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, AgentRequest, AgentResponse, Evidence, Stage
from autoresearch.engine import Engine
from autoresearch.literature import Literature
from autoresearch.store import Store


class InjectedLiterature(Literature):
    def __init__(self, config: ResearchConfig, tag: str = "injected", interrupt: bool = False):
        super().__init__(config, providers=[])
        self.tag, self.interrupt = tag, interrupt
        self.queries: list[str] = []

    def behavior_identity(self) -> dict[str, Any]:
        return {**super().behavior_identity(), "source": self.tag}

    def search(self, query: str, count: int = 40) -> list[Evidence]:
        self.queries.append(query)
        self.search_history.append(
            {
                "query": query,
                "cutoff": self.publication_cutoff,
                "retrieved_at": "2024-12-31T00:00:00Z",
                "evidence_ids": [self.tag],
                "exhaustive": False,
                "providers": [{"provider": self.tag, "status": "completed"}],
                "limitations": [],
            }
        )
        if self.interrupt:
            self.search_history[-1]["providers"][0]["status"] = "failed"
            raise RuntimeError("synthetic retrieval interruption")
        return [
            Evidence(
                id=self.tag,
                title="Injected eligible paper",
                url="https://arxiv.org/abs/2401.00001",
                published_at="2024-01-01",
                abstract="INJECTED_EVIDENCE_MARKER",
                provider=self.tag,
            )
        ]


class ReviewProvider:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    def behavior_identity(self) -> dict[str, str]:
        return {"model": "synthetic-review-fixture"}

    def complete(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        output = AgentOutput(summary=request.role, confidence=1, score=4)
        if request.role.endswith("questions"):
            output.plans = [{"question": f"Independent question {i}?"} for i in range(5)]
        else:
            output.structured = {"claims": ["claim"], "method": "method", "evidence": []}
            if request.role.endswith("answers"):
                output.evidence_ids = ["injected"]
        return AgentResponse(data=output.model_dump(), provider="fixture", model="fixture")


@pytest.mark.parametrize("interrupt", [False, True])
def test_default_engine_runner_preserves_injected_retrieval_and_resume_identity(
    tmp_path: Path, interrupt: bool
) -> None:
    config = ResearchConfig(search_enabled=False)
    config.pipeline.critics = 1
    config.scholarpeer.publication_cutoff = "2024-12-31"
    config.literature.publication_cutoff = "2024-06-30"
    provider = ReviewProvider()
    literature = InjectedLiterature(config, interrupt=interrupt)
    literature.search_history.append({"query": "earlier novelty query", "providers": []})
    store = Store(tmp_path / "private")
    engine = Engine(store, config, provider=provider, literature=literature)
    state = engine.create("Synthetic study", "Test actual retrieval dependency")
    state.stage = Stage.PEER_REVIEW
    state.manuscript = "Synthetic manuscript with measured evidence. " * 4
    store.save(state, "fixture_checkpoint")
    original_identity = behavior.recorded(store, state)["extensions"]["literature"]

    result = engine.step(state.id)
    assert literature.queries, "ScholarPeer bypassed the injected retrieval adapter"
    assert literature.publication_cutoff == "2024-06-30"
    assert engine._behavior_extensions(config)["literature"] == original_identity
    checkpoints = [a for a in store.artifacts(state.id) if a["kind"] == "scholarpeer_checkpoint"]
    snapshot = json.loads(store.artifact_content(state.id, checkpoints[-1]["id"]))
    assert snapshot["publication_cutoff"] == "2024-12-31"
    assert all(report["query"] != "earlier novelty query" for report in snapshot["search_reports"])
    assert literature.search_history[0]["query"] == "earlier novelty query"
    if interrupt:
        assert result.status == "blocked" and "synthetic retrieval interruption" in result.error
        assert snapshot["status"] == "failed"
        assert snapshot["search_reports"][-1]["providers"][0]["status"] == "failed"
    else:
        assert result.status == "ready" and result.stage == Stage.REBUTTAL_PLAN
        engine.intervene(state.id, "Review retained scientific evidence", stage=Stage.PEER_REVIEW)

    replacement = InjectedLiterature(config)
    resumed = Engine(store, provider=provider, literature=replacement)
    resumed.resume(state.id)
    result = resumed.step(state.id)
    assert result.status == "ready" and result.stage == Stage.REBUTTAL_PLAN
    assert replacement.queries
    assert replacement.publication_cutoff == "2024-06-30"
    behavior.verify(store, result, config, extensions=resumed._behavior_extensions(config))
    review_requests = [
        request for request in provider.requests if request.role == "review_literature"
    ]
    assert review_requests and all(
        "INJECTED_EVIDENCE_MARKER" in request.prompt for request in review_requests
    )
    all_reports = [
        report
        for request in review_requests
        for report in json.loads(request.prompt)["search_reports"]
    ]
    assert all(report["providers"][0]["provider"] == "injected" for report in all_reports)

    count = len(provider.requests)
    changed = Engine(store, provider=provider, literature=InjectedLiterature(config, tag="changed"))
    blocked = changed.step(state.id)
    assert blocked.status == "blocked" and "behavior changed" in blocked.error
    assert len(provider.requests) == count


@pytest.mark.parametrize("supplied", ["omitted", "changed"])
def test_direct_review_runner_cannot_replace_pinned_retrieval(
    tmp_path: Path, supplied: str
) -> None:
    from autoresearch.agents import AgentRunner

    config = ResearchConfig(search_enabled=False)
    provider = ReviewProvider()
    original = InjectedLiterature(config)
    store = Store(tmp_path / "private")
    state = Engine(store, config, provider=provider, literature=original).create(
        "Synthetic study", "Protect direct review calls"
    )
    adapter = None if supplied == "omitted" else InjectedLiterature(config, tag="changed")
    runner = AgentRunner(store, config, provider, literature=adapter)
    with pytest.raises(ValueError, match="retrieval adapter differs"):
        runner.run(state, "peer_review")
    assert not provider.requests and not original.queries
    if adapter is not None:
        assert not adapter.queries
