"""Cached scientific outputs retain the producing call's actual identity."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, AgentResponse, ProviderConfig, RunState
from autoresearch.store import Store


class RecordedProvider:
    def __init__(self, *, repair: bool = False, frontier: bool = False):
        self.requests = []
        self.repair, self.frontier = repair, frontier

    def complete(self, request):
        self.requests.append(request.model_copy(deep=True))
        invalid = (self.repair and len(self.requests) == 1) or (
            self.frontier and request.provenance["route"] != "frontier"
        )
        output = AgentOutput(
            summary="Synthetic recorded conclusion",
            limitations=[] if invalid else ["Needs additional controls"],
        )
        return AgentResponse(
            data=output.model_dump(),
            model="actual-fixture-model",
            provider="actual-fixture-provider",
        )


def fixture(tmp_path, config, provider=None):
    store = Store(tmp_path)
    state = RunState(id="abcdef123456", title="Synthetic fixture", objective="Keep provenance")
    store.create(state, config)
    return store, state, AgentRunner(store, config, provider)


def event(store, state, kind):
    return [item["payload"] for item in store.events(state.id) if item["kind"] == kind][-1]


@pytest.mark.parametrize("demo", [True, False])
def test_cache_records_actual_demo_and_injected_provider_identity(tmp_path, demo):
    config = ResearchConfig(mode="demo" if demo else "live")
    provider = None if demo else RecordedProvider()
    store, state, runner = fixture(tmp_path, config, provider)
    first = runner._one(state, "limitations", {}, 0)
    producing = event(store, state, "agent_completed")
    calls = store.usage(state.id)["calls"]
    assert runner._one(state, "limitations", {}, 0) == first
    reused = event(store, state, "agent_cache")
    assert (reused["model"], reused["provider"]) == (producing["model"], producing["provider"])
    assert reused["call_id"] == producing["call_id"]
    assert reused["provenance_status"] == "recorded"
    assert reused["configured_model"] == config.provider.model
    assert store.usage(state.id)["calls"] == calls


def test_cache_records_actual_command_adapter_identity(tmp_path: Path):
    payload = AgentResponse(
        data=AgentOutput(summary="Synthetic adapter", limitations=["Unmeasured"]).model_dump(),
        model="adapter-model",
        provider="adapter-provider",
    ).model_dump_json()
    config = ResearchConfig(
        role_commands={"limitations": [sys.executable, "-c", f"print({payload!r})"]},
        role_command_max_cost_usd={"limitations": 0},
    )
    store, state, runner = fixture(tmp_path, config)
    runner._one(state, "limitations", {}, 0)
    runner._one(state, "limitations", {}, 0)
    reused = event(store, state, "agent_cache")
    assert (reused["model"], reused["provider"]) == ("adapter-model", "adapter-provider")
    assert reused["call_id"] == event(store, state, "agent_completed")["call_id"]
    assert store.usage(state.id)["calls"] == 1


def test_cache_preserves_successful_repair_request_separately_from_lookup(tmp_path):
    provider = RecordedProvider(repair=True)
    store, state, runner = fixture(tmp_path, ResearchConfig(), provider)
    first = runner._one(state, "limitations", {}, 0)
    producing = event(store, state, "agent_completed")
    assert runner._one(state, "limitations", {}, 0) == first
    reused = event(store, state, "agent_cache")
    assert len(provider.requests) == 2
    assert reused["request_sha256"] == producing["request_sha256"]
    assert reused["request_sha256"] != reused["lookup_request_sha256"]
    assert reused["call_id"] == producing["call_id"]


def test_escalated_cache_keeps_frontier_call_identity(tmp_path):
    provider = RecordedProvider(frontier=True)
    config = ResearchConfig(frontier_provider=ProviderConfig(model="configured-frontier"))
    config.pipeline.max_agent_repairs = 0
    store, state, runner = fixture(tmp_path, config, provider)
    first = runner._one(state, "limitations", {}, 0)
    frontier = event(store, state, "agent_completed")
    assert runner._one(state, "limitations", {}, 0) == first
    reused = event(store, state, "agent_cache")
    # The second rejected default attempt remains a separately accounted call;
    # the successful frontier result is reused under its existing logical key.
    assert len(provider.requests) == 3
    assert reused["route"] == "frontier"
    assert reused["model"] == frontier["model"]
    assert reused["call_id"] == frontier["call_id"]
    assert reused["request_sha256"] == frontier["request_sha256"]


def test_legacy_cache_remains_usable_without_fabricating_response_provenance(tmp_path):
    provider = RecordedProvider()
    config = ResearchConfig()
    store, state, runner = fixture(tmp_path, config, provider)
    first = runner._one(state, "limitations", {}, 0)
    key = event(store, state, "agent_started")["cache_key"]
    store.cache_put(key, first.model_dump())
    assert runner._one(state, "limitations", {}, 0) == first
    reused = event(store, state, "agent_cache")
    assert len(provider.requests) == 1
    assert reused["provenance_status"] == "legacy_unknown"
    assert reused["model"] is None and reused["provider"] is None
    assert reused["call_id"] is None and "request_sha256" not in reused
    assert reused["configured_model"] == config.provider.model
    assert reused["configured_provider"] == config.provider.name
