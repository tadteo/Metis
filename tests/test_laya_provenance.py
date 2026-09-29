"""Typed advisory transport receipts bind the actual questions and configured model."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest

from autoresearch.agents import AgentRunner
from autoresearch.catalog import ROOT, load_catalog
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, AgentRequest, AgentResponse, RunState, Usage
from autoresearch.laya import LayaClient, triage
from autoresearch.providers import ProviderError
from autoresearch.store import Store


def setup(
    tmp_path: Path, config: ResearchConfig | None = None
) -> tuple[Store, RunState, ResearchConfig]:
    config = config or ResearchConfig()
    config.mode = "live"
    config.laya.enabled = True
    config.search_enabled = False
    store = Store(tmp_path / "private")
    state = RunState(id="abcdefabcdef", title="Typed fixture", objective="Synthetic contract check")
    store.create(state, config)
    return store, state, config


def test_actual_typed_request_has_prompt_model_and_version_receipts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = ResearchConfig(prompt_overrides={"laya_triage": "Is the PRIVATE evidence unresolved?"})
    config.privacy.redact_patterns = ["PRIVATE"]
    config.laya.model = "fixture-typed"
    store, state, config = setup(tmp_path, config)
    requests: list[dict[str, Any]] = []

    def decide(
        self: LayaClient, state: dict[str, Any], questions: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        requests.append(
            {
                "state": state,
                "questions": questions,
                "model": self.config.model,
                "max_len": self.config.max_len,
            }
        )
        return {"answers": {"needs_deeper_analysis": {"noul": 0.8}}}, Usage(input_tokens=12)

    monkeypatch.setattr(LayaClient, "decide", decide)
    result = triage(
        store, state.id, "filter_ideas", config.laya, {"evidence": "PRIVATE synthetic evidence"}
    )
    assert result["advisory_only"] is True
    assert (
        requests[0]["questions"]["needs_deeper_analysis"]["instructions"]
        == "Is the [REDACTED] evidence unresolved?"
    )
    assert requests[0]["state"]["evidence"] == "[REDACTED] synthetic evidence"
    event = next(
        event["payload"] for event in store.events(state.id) if event["kind"] == "agent_completed"
    )
    assert (
        event["request_sha256"]
        == hashlib.sha256(json.dumps(requests[0], sort_keys=True).encode()).hexdigest()
    )
    assert (
        event["prompt_sha256"]
        == hashlib.sha256(json.dumps(requests[0]["questions"], sort_keys=True).encode()).hexdigest()
    )
    assert event["model"] == "fixture-typed"
    assert event["schema_version"] == "LayaDecision.v1"
    assert event["catalog_sha256"] == load_catalog().digest
    assert event["call_id"] and event["agent_sha256"] and event["agent_version"]
    assert (
        triage(
            store, state.id, "filter_ideas", config.laya, {"evidence": "PRIVATE synthetic evidence"}
        )
        == result
    )
    assert len(requests) == 1
    assert any(event["kind"] == "agent_cache" for event in store.events(state.id))


def test_prompt_revision_invalidates_typed_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, state, config = setup(tmp_path)
    calls: list[dict[str, Any]] = []

    def decide(
        self: LayaClient, state: dict[str, Any], questions: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        calls.append(questions)
        return {"answers": {"needs_deeper_analysis": {"noul": 0.5}}}, Usage()

    monkeypatch.setattr(LayaClient, "decide", decide)
    custom = tmp_path / "specs"
    shutil.copytree(ROOT, custom)
    triage(store, state.id, "filter_ideas", config.laya, {}, catalog=load_catalog(custom))
    (custom / "prompts/laya_triage.md").write_text(
        "Does the revised evidence require scientific review?"
    )
    triage(store, state.id, "filter_ideas", config.laya, {}, catalog=load_catalog(custom))
    assert len(calls) == 2 and calls[0] != calls[1]


def test_typed_transport_respects_cache_opt_out_and_preserves_failed_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = ResearchConfig()
    config.privacy.cache = False
    config.laya.cost_per_call_usd = 0.1
    store, state, config = setup(tmp_path, config)
    calls = []

    def decide(
        self: LayaClient, state: dict[str, Any], questions: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        calls.append(questions)
        if len(calls) == 2:
            raise ProviderError(
                "Unresolved typed request", usage=Usage(cost_usd=0.1, estimated=True)
            )
        return {"answers": {"needs_deeper_analysis": {"noul": 0.5}}}, Usage(cost_usd=0.1)

    monkeypatch.setattr(LayaClient, "decide", decide)
    triage(store, state.id, "filter_ideas", config.laya, {})
    result = triage(store, state.id, "filter_ideas", config.laya, {})
    assert len(calls) == 2 and result["escalate"] is True
    event = next(
        event["payload"] for event in store.events(state.id) if event["kind"] == "model_escalation"
    )
    assert event["usage"]["cost_usd"] == 0.1
    assert event["request_sha256"] and event["prompt_sha256"] and event["agent_sha256"]


def test_advisory_result_never_skips_primary_scientific_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, state, config = setup(tmp_path)
    requests: list[AgentRequest] = []

    class ScientificProvider:
        def complete(self, request: AgentRequest) -> AgentResponse:
            requests.append(request)
            context = json.loads(request.prompt)
            assert context["laya_triage"]["advisory_only"] is True
            return AgentResponse(
                data=AgentOutput(summary="Independent scientific critique").model_dump(),
                provider="fixture",
                model="fixture",
            )

    monkeypatch.setattr(
        LayaClient,
        "decide",
        lambda *args: ({"answers": {"needs_deeper_analysis": {"noul": 0.0}}}, Usage()),
    )
    runner = AgentRunner(store, config, ScientificProvider())
    runner.run(state, "filter_ideas")
    assert requests
    advisory = runner.run(state, "laya_triage", {"role": "fixture"})
    assert advisory.decision == "refine" and advisory.structured["advisory_only"] is True


@pytest.mark.parametrize("answer", [True, "0.8", -0.1, 1.1])
def test_laya_rejects_invalid_typed_values_with_conservative_usage(answer: Any) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answers": {"triage": {"noul": answer}}})

    config = ResearchConfig().laya
    config.cost_per_call_usd = 0.2
    client = LayaClient(config, httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(ProviderError) as failure:
        client.decide({}, {"triage": {"type": "noul", "instructions": "Fixture"}})
    assert failure.value.usage.cost_usd == 0.2


def test_wire_payload_hashes_match_receipts_and_oversize_is_never_truncated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, state, config = setup(tmp_path)
    wire: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        wire.append(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"needs_deeper_analysis": {"noul": 0.5}}})

    client = LayaClient(config.laya, httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr("autoresearch.laya.LayaClient", lambda config: client)
    evidence = {"evidence": "x" * (config.laya.max_input_chars - 100)}
    triage(store, state.id, "filter_ideas", config.laya, evidence)
    assert wire[0]["state"] == evidence
    completed = next(
        event["payload"] for event in store.events(state.id) if event["kind"] == "agent_completed"
    )
    assert (
        completed["request_sha256"]
        == hashlib.sha256(json.dumps(wire[0], sort_keys=True).encode()).hexdigest()
    )
    assert (
        completed["prompt_sha256"]
        == hashlib.sha256(json.dumps(wire[0]["questions"], sort_keys=True).encode()).hexdigest()
    )
    oversized = {"evidence": "x" * config.laya.max_input_chars}
    result = triage(store, state.id, "filter_ideas", config.laya, oversized)
    assert not result["available"] and result["escalate"] is True
    assert len(wire) == 1
    failure = next(
        event["payload"] for event in store.events(state.id) if event["kind"] == "model_escalation"
    )
    assert "without truncating" in failure["reason"]
    assert failure["usage"]["cost_usd"] == 0
