"""Offline failures exercise real transport, reservations and successful provenance."""

import json

import httpx
import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, ProviderConfig, RunState
from autoresearch.model_inventory import AvailableModel, ModelInventory
from autoresearch.providers import CompatibleProvider, ProviderError
from autoresearch.store import Store


def setup(tmp_path, monkeypatch, statuses):
    providers = [
        ProviderConfig(
            name="fixture",
            model=name,
            base_url="http://localhost/" + name,
            retries=0,
            max_output_tokens=256,
        )
        for name in ("cheap", "backup", "third", "excluded")
    ]
    config = ResearchConfig(
        provider=providers[0],
        model_inventory=ModelInventory(
            models=[AvailableModel(id=p.model, label=p.model, provider=p) for p in providers]
        ),
        allowed_models=["cheap", "backup", "third"],
    )
    config.pipeline.max_agent_repairs = 0
    store = Store(tmp_path / "state")
    state = RunState(id="0123456789ab", title="Synthetic", objective="Offline")
    store.create(state, config)
    seen = []

    def transport(request):
        model = json.loads(request.content)["model"]
        seen.append(model)
        status = statuses.get(model, 200)
        if callable(status):
            return status(request)
        return httpx.Response(
            status,
            json={
                "choices": [
                    {
                        "message": {
                            "content": AgentOutput(
                                summary="Checked",
                                confidence=1,
                                limitations=["Synthetic limitation"],
                            ).model_dump_json()
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(
        "autoresearch.agents.CompatibleProvider",
        lambda cfg: CompatibleProvider(
            cfg, client=httpx.Client(transport=httpx.MockTransport(transport))
        ),
    )
    return store, state, config, seen


def test_failure_switches_and_accounts_actual_cached_model(tmp_path, monkeypatch):
    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": 429})
    runner = AgentRunner(s, c)
    assert runner._one(x, "limitations", {}, 0).summary == "Checked"
    assert seen == ["cheap", "backup"]
    assert s.usage(x.id)["calls"] == 2
    assert s.usage(x.id)["reserved_usd"] == 0
    assert s.usage(x.id)["cost_usd"] > 0
    runner._one(x, "limitations", {}, 0)
    assert seen == ["cheap", "backup"]
    events = s.events(x.id)
    assert any(e["kind"] == "provider_fallback" for e in events)
    assert [e for e in events if e["kind"] == "agent_cache"][-1]["payload"]["model"] == "backup"


@pytest.mark.parametrize("status", [429, 503, 500])
def test_all_failures_are_bounded_and_charged(tmp_path, monkeypatch, status):
    s, x, c, seen = setup(
        tmp_path, monkeypatch, {name: status for name in ("cheap", "backup", "third", "excluded")}
    )
    runner = AgentRunner(s, c)
    with pytest.raises(ProviderError):
        runner._one(x, "limitations", {}, 0)
    assert seen == ["cheap", "backup", "third"]
    assert s.usage(x.id)["calls"] == 3
    assert s.usage(x.id)["reserved_usd"] == 0
    with pytest.raises(ProviderError, match="cooling down"):
        runner._one(x, "limitations", {}, 0)
    assert len(seen) == 3


@pytest.mark.parametrize("status", [400, 401, 403])
def test_auth_or_invalid_request_does_not_switch(tmp_path, monkeypatch, status):
    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": status})
    with pytest.raises(ProviderError):
        AgentRunner(s, c)._one(x, "limitations", {}, 0)
    assert seen == ["cheap"]


@pytest.mark.parametrize(
    "protection", ["explicit", "panel", "heldout", "frontier", "one_allowed", "disabled"]
)
def test_fixed_routes_and_permissions_are_preserved(tmp_path, monkeypatch, protection):
    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": 503})
    role = "limitations"
    frontier = False
    if protection == "explicit":
        c.model_inventory = None
    elif protection == "panel":
        c.role_panels[role] = [c.provider]
    elif protection == "heldout":
        role = "heldout_review"
        c.heldout_provider = c.provider
    elif protection == "frontier":
        c.frontier_provider = c.provider
        frontier = True
    elif protection == "one_allowed":
        c.allowed_models = ["cheap"]
    else:
        for entry in c.model_inventory.models[1:]:
            entry.enabled = False
    with pytest.raises(ProviderError):
        AgentRunner(s, c)._one(x, role, {}, 0, frontier)
    assert seen == ["cheap"]


def test_budget_and_pause_prevent_fallback_dispatch(tmp_path, monkeypatch):
    from autoresearch.coding import CodingPending
    from autoresearch.store import BudgetExceeded

    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": 429})
    c.budget.max_calls = 1
    # Store's saved budget, rather than a runner-local value, controls dispatch.
    with s.connect() as db:
        db.execute("UPDATE runs SET config=? WHERE id=?", (c.model_dump_json(), x.id))
    with pytest.raises(BudgetExceeded):
        AgentRunner(s, c)._one(x, "limitations", {}, 0)
    assert seen == ["cheap"]
    s.set_paused(x.id, True)
    with pytest.raises(CodingPending):
        AgentRunner(s, c)._one(x, "limitations", {}, 0)
    assert seen == ["cheap"]


def test_transport_failure_conservatively_charged_before_switch(tmp_path, monkeypatch):
    def disconnected(request):
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": disconnected})
    AgentRunner(s, c)._one(x, "limitations", {}, 0)
    failure = next(e for e in s.events(x.id) if e["kind"] == "agent_provider_failed")
    assert failure["payload"]["usage"]["estimated"]
    assert failure["payload"]["usage"]["cost_usd"] > 0
    assert seen == ["cheap", "backup"]


def test_failure_projection_is_failed_not_completed(tmp_path, monkeypatch):
    from autoresearch.process_view import process_view

    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": 429})
    AgentRunner(s, c)._one(x, "limitations", {}, 0)
    rows = [r for r in process_view(s, x.id)["rows"] if r["kind"] == "call"]
    assert [r["status"] for r in rows] == ["failed", "completed"]
    assert [r["record"]["model"] for r in rows] == ["cheap", "backup"]


def test_invalid_output_then_failed_frontier_does_not_trigger_availability_fallback(
    tmp_path, monkeypatch
):
    def invalid(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": AgentOutput(
                                summary="No limitations", confidence=1
                            ).model_dump_json()
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": invalid, "backup": 503})
    c.frontier_provider = c.model_inventory.models[1].provider
    with pytest.raises(ProviderError):
        AgentRunner(s, c)._one(x, "limitations", {}, 0)
    assert seen == ["cheap", "backup"]


def test_inherited_heldout_and_command_calls_do_not_switch(tmp_path, monkeypatch):
    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": 503})
    with pytest.raises(ProviderError):
        AgentRunner(s, c)._one(x, "artifact_selector", {"original_role": "heldout_review"}, 0)
    assert seen == ["cheap"]
    c.role_commands["limitations"] = ["synthetic-command"]
    c.role_command_max_cost_usd["limitations"] = 1
    runner = AgentRunner(s, c)

    def failed(*args):
        raise ProviderError("Synthetic command failure", recoverable=True)

    monkeypatch.setattr(runner, "_command", failed)
    with pytest.raises(ProviderError):
        runner._one(x, "limitations", {}, 0)
    assert seen == ["cheap"]


def test_operator_pause_during_failed_call_stops_switch(tmp_path, monkeypatch):
    from autoresearch.coding import CodingPending

    s, x, c, seen = setup(tmp_path, monkeypatch, {})

    # Patch the shared transport to simulate a pause arriving while request is in flight.
    def paused(request):
        s.set_paused(x.id, True)
        return httpx.Response(429, json={})

    monkeypatch.setattr(
        "autoresearch.agents.CompatibleProvider",
        lambda cfg: CompatibleProvider(
            cfg, client=httpx.Client(transport=httpx.MockTransport(paused))
        ),
    )
    with pytest.raises(CodingPending):
        AgentRunner(s, c)._one(x, "limitations", {}, 0)
    assert s.usage(x.id)["calls"] == 1
    assert s.usage(x.id)["reserved_usd"] == 0


def test_cooldown_expires_without_excluding_model_permanently(tmp_path, monkeypatch):
    from types import SimpleNamespace

    clock = [100.0]
    monkeypatch.setattr("autoresearch.agents.time", SimpleNamespace(monotonic=lambda: clock[0]))
    s, x, c, seen = setup(tmp_path, monkeypatch, {"cheap": 429})
    runner = AgentRunner(s, c)
    runner._one(x, "limitations", {}, 0)
    clock[0] += 61
    runner._one(x, "limitations", {}, 0)
    assert seen == ["cheap", "backup", "cheap"]  # Backup's validated response is cached.
