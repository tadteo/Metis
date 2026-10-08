"""Automatic per-role model selection: deterministic planner, validated router, stats.

Offline only: the planner reads local configuration and the published preset catalog;
router calls go to an httpx MockTransport. Nothing here measures research quality.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest
from test_agent_catalog import copied_catalog

from autoresearch.agents import AgentRunner, quota_key
from autoresearch.behavior import inspect_run
from autoresearch.catalog import load_catalog
from autoresearch.config import ModelSelectionConfig, ResearchConfig
from autoresearch.contracts import AgentOutput, ProviderConfig, RunState, Stage
from autoresearch.engine import Engine
from autoresearch.model_inventory import (
    AvailableModel,
    ModelInventory,
    initial_inventory,
    plan_and_prepare,
)
from autoresearch.model_selection import (
    ROUTER_ROLE,
    apply_model_plan,
    outcome_stats,
    validate_routes,
)
from autoresearch.provider_presets import add_to_inventory, find, to_entry
from autoresearch.providers import CompatibleProvider, ProviderError
from autoresearch.routing import ResolvedRoute, fallback_routes, resolve_route
from autoresearch.setup import preflight
from autoresearch.store import Store, now
from autoresearch.system_view import system_text

MIXED = (
    "google:gemini-3.8-flash",
    "google:gemini-3.6-flash",
    "mistral:mistral-small-latest",
    "mistral:mistral-medium-latest",
    "groq:openai/gpt-oss-120b",
    "cerebras:gpt-oss-120b",
    "openrouter:nvidia/nemotron-3-super-120b-a12b:free",
)
CODING = ("baseline", "subset", "full", "ablation", "rebuttal", "meta_refine")


@pytest.fixture
def keys(monkeypatch):
    """Every provider key is present except the default xAI one; no value is read."""
    monkeypatch.setattr(
        "autoresearch.credentials.resolve",
        lambda name: ("" if name == "XAI_API_KEY" else "fixture-key-only", "environment"),
    )


def presets(*references: str, tier: str = "free", base: ResearchConfig | None = None):
    inventory = initial_inventory(base or ResearchConfig())
    for reference in references:
        provider, model = find(reference)
        inventory = add_to_inventory(inventory, to_entry(provider, model, tier=tier))  # type: ignore[arg-type]
    return inventory


def mixed_config(*extra: str) -> ResearchConfig:
    return ResearchConfig(model_inventory=presets(*MIXED, *extra))


def entry_id(config: ResearchConfig, model: str) -> str:
    assert config.model_inventory is not None
    return next(m.id for m in config.model_inventory.models if m.provider.model == model)


# Planner constraints ------------------------------------------------------------------


def test_planner_applies_context_tpm_json_and_critical_tier_constraints(keys):
    config = mixed_config(
        "openrouter:nvidia/nemotron-3-ultra-550b-a55b:free", "google:gemini-3.5-flash-lite"
    )
    prepared, plan = plan_and_prepare(config)
    assert plan is not None
    groq = entry_id(config, "openai/gpt-oss-120b")
    cerebras = entry_id(config, "gpt-oss-120b")
    ultra = entry_id(config, "nvidia/nemotron-3-ultra-550b-a55b:free")
    lite = entry_id(config, "gemini-3.5-flash-lite")
    for role, item in plan["roles"].items():
        # Groq free: 8,000 tokens/minute cannot carry any estimated Metis request.
        assert any("tokens/minute" in r for r in item["excluded"][groq]), role
        # Published JSON mode is off for this free model.
        assert "no JSON mode" in item["excluded"][ultra]
        if item["class"] == "critical":
            assert lite not in item["eligible"]
            assert any("critical floor" in r for r in item["excluded"][lite])
    for role in CODING:
        # Cerebras free context (65k) cannot hold a ~56k-token coding prompt plus margin.
        assert any("context window" in r for r in plan["roles"][role]["excluded"][cerebras])
    # The default xAI primary has no key: the default route and frontier escalation use
    # the model carrying most critical work, so escalations fit critical requests.
    from autoresearch.model_selection import workhorse

    chosen = next(m for m in prepared.model_inventory.models if m.id == workhorse(plan))
    assert prepared.provider == chosen.provider == prepared.frontier_provider
    # Frozen routes contain only eligible models, primary first.
    assert prepared.planned_routes is not None
    for role, order in prepared.planned_routes.items():
        assert order[0] == plan["roles"][role]["primary"]
        assert set(order) == set(plan["roles"][role]["eligible"])
        assert resolve_route(prepared, role).provider.model == next(
            m.provider.model for m in prepared.model_inventory.models if m.id == order[0]
        )


def test_critical_roles_never_route_to_a_light_model(keys):
    provider, model = find("google:gemini-3.5-flash-lite")
    entry = to_entry(provider, model)
    config = ResearchConfig(provider=entry.provider, model_inventory=ModelInventory(models=[entry]))
    with pytest.raises(ValueError, match="capability floor for the critical role"):
        plan_and_prepare(config)


def test_free_tier_is_preferred_and_paid_charges_are_estimated(keys):
    provider, model = find("mistral:mistral-medium-latest")
    inventory = add_to_inventory(
        presets("google:gemini-3.8-flash"), to_entry(provider, model, tier="paid")
    )
    config = ResearchConfig(model_inventory=inventory)
    config.budget.usd = 1000
    _, plan = plan_and_prepare(config)
    assert plan is not None
    gemini = entry_id(config, "gemini-3.8-flash")
    mistral = entry_id(config, "mistral-medium-latest")
    assert plan["models"][gemini]["plan"] == "free"
    assert plan["models"][mistral]["plan"] == "paid"
    # Both are provider-described as strong; the free tier is used up to one day of its
    # quota, and the rest spills to the paid plan, as runtime fallback would.
    free_roles = [r for r in plan["roles"].values() if r["primary"] == gemini]
    paid_roles = [r for r in plan["roles"].values() if r["primary"] == mistral]
    assert free_roles and all(r["estimated_charge_usd"] == 0 for r in free_roles)
    assert paid_roles, "the 20 requests/day free quota cannot carry the whole run"
    assert all(r["estimated_charge_usd"] > 0 for r in paid_roles)
    assert plan["totals"]["per_model"][gemini]["expected_calls"] <= 20
    assert plan["totals"]["days"] == 1
    assert any("already planned for a full day" in r["why"] for r in paid_roles)
    assert plan["warnings"] == []
    # A tight budget keeps paid models as fallbacks: the free quota takes longer instead.
    config.budget.usd = 1
    _, tight = plan_and_prepare(config)
    assert tight["totals"]["estimated_charge_usd"] <= 1
    assert tight["totals"]["days"] > 1 and tight["warnings"] == []
    for item in tight["roles"].values():
        assert mistral in item["eligible"]


def test_planner_warns_when_charge_exceeds_budget(keys):
    provider, model = find("mistral:mistral-medium-latest")
    config = ResearchConfig(
        model_inventory=add_to_inventory(
            initial_inventory(ResearchConfig()), to_entry(provider, model, tier="paid")
        )
    )
    config.budget.usd = 0.5
    _, plan = plan_and_prepare(config)
    assert plan["totals"]["estimated_charge_usd"] > 0.5
    assert any("exceeds the run budget" in w for w in plan["warnings"])
    # The router may repeat an over-budget planner plan, but never raise its charge.
    routes = {
        role: {"primary": item["primary"], "fallbacks": [], "rationale": "Same as planner."}
        for role, item in plan["roles"].items()
    }
    frozen = ResearchConfig(planned_routes={r: i["eligible"] for r, i in plan["roles"].items()})
    frozen.budget.usd = 0.5
    assert validate_routes(frozen, plan, routes)[2] == []


def test_critical_roles_keep_the_floor_when_no_model_fits_the_size(keys):
    # Light primary plus a strong model that no request fits (8k tokens/minute).
    lite_provider, lite = find("google:gemini-3.5-flash-lite")
    entry = to_entry(lite_provider, lite)
    groq_provider, groq = find("groq:openai/gpt-oss-120b")
    config = ResearchConfig(
        provider=entry.provider,
        model_inventory=ModelInventory(models=[entry, to_entry(groq_provider, groq)]),
    )
    prepared, plan = plan_and_prepare(config)
    groq_id = entry_id(config, "openai/gpt-oss-120b")
    lite_id = entry_id(config, "gemini-3.5-flash-lite")
    for role, item in plan["roles"].items():
        if item["class"] == "critical" or role == ROUTER_ROLE:
            assert item["primary"] == groq_id and lite_id not in item["eligible"], role
    assert any("request-size guard decides" in w for w in plan["warnings"])
    totals = plan["totals"]
    assert totals["estimated_charge_usd"] == pytest.approx(
        sum(r["estimated_charge_usd"] for r in plan["roles"].values()), abs=0.01
    )
    assert totals["estimated_list_cost_usd"] >= totals["estimated_charge_usd"]


def test_quota_spreading_and_days_estimate(keys):
    config = ResearchConfig(
        model_inventory=presets(
            "google:gemini-3.8-flash", "openrouter:nvidia/nemotron-3-super-120b-a12b:free"
        )
    )
    _, plan = plan_and_prepare(config)
    assert plan is not None
    gemini = entry_id(config, "gemini-3.8-flash")
    nemotron = entry_id(config, "nvidia/nemotron-3-super-120b-a12b:free")
    per_model = plan["totals"]["per_model"]
    # Both free models carry work: requests are spread across the two daily quotas.
    assert per_model[gemini]["expected_calls"] > 0 and per_model[nemotron]["expected_calls"] > 0
    assert per_model[gemini]["requests_per_day"] == 20
    assert per_model[nemotron]["requests_per_day"] == 50
    days = {m: v["expected_calls"] / v["requests_per_day"] for m, v in per_model.items()}
    assert plan["totals"]["days"] == math.ceil(max(days.values()))
    assert plan["totals"]["days"] > 1 and plan["totals"]["binding_model"] in days
    # Spreading keeps both quotas within one day of each other.
    assert abs(days[gemini] - days[nemotron]) <= 1.5
    assert plan["models"][gemini]["requests_per_day_basis"] == "observed"


def test_data_use_caveat_can_exclude_free_tiers(keys):
    config = mixed_config()
    config.model_selection = ModelSelectionConfig(exclude_data_use_caveats=True)
    # Without a caveat-free model that fits coding prompts, creation fails clearly
    # instead of sending private research to an excluded free tier.
    with pytest.raises(ValueError, match="data-use setting"):
        plan_and_prepare(config)
    provider, model = find("mistral:mistral-large-4")
    assert config.model_inventory is not None
    config.model_inventory = add_to_inventory(
        config.model_inventory, to_entry(provider, model, tier="paid")
    )
    config.budget.usd = 1000
    _, plan = plan_and_prepare(config)
    assert plan is not None
    for item in plan["roles"].values():
        for model_id in item["eligible"]:
            facts = plan["models"][model_id]
            assert not (facts["plan"] == "free" and facts["data_use"])


def test_protected_and_explicit_routes_are_untouched(keys, tmp_path):
    config = mixed_config()
    medium = next(m for m in config.model_inventory.models if "medium" in m.provider.model)
    small = next(m for m in config.model_inventory.models if "small" in m.provider.model)
    config.role_providers["select"] = small.provider
    config.role_panels["subset_critic"] = [medium.provider, small.provider]
    config.heldout_provider = small.provider
    config.frontier_provider = medium.provider
    prepared, plan = plan_and_prepare(config)
    assert plan is not None
    fixed = plan["fixed_roles"]
    assert fixed["select"] == "explicit role override"
    assert fixed["subset_critic"] == "explicit panel keeps its configured models"
    assert fixed["heldout_review"].startswith("held-out evaluator")
    assert fixed["coding_step"] == "uses the calling role's route"
    assert fixed["draft"].startswith("native manuscript writer")
    assert prepared.role_providers["select"] == small.provider
    assert prepared.role_panels["subset_critic"] == [medium.provider, small.provider]
    assert prepared.heldout_provider == small.provider
    assert prepared.frontier_provider == medium.provider
    assert not set(fixed) & set(prepared.planned_routes or {})


def test_disabled_selection_keeps_previous_cost_routing(keys):
    config = mixed_config()
    config.model_selection = ModelSelectionConfig(enabled=False)
    prepared, plan = plan_and_prepare(config)
    assert plan is None and prepared.planned_routes is None
    assert prepared.role_providers["limitations"] == prepared.cheap_provider


def test_setup_preview_shows_plan_without_model_call(keys, monkeypatch):
    monkeypatch.setattr(
        CompatibleProvider, "complete", lambda *_: pytest.fail("planning must not call a model")
    )
    report = preflight(mixed_config())
    check = next(c for c in report["checks"] if c["name"] == "model-plan")
    assert "no model call" in check["message"] and "Estimates, not measurements" in check["message"]
    assert {row["role"] for row in report["model_plan"]["routes"]} >= {"limitations", "subset"}


# Run lifecycle ------------------------------------------------------------------------


def fixture_run(tmp_path, monkeypatch, router_reply, *, selection=None, models=3):
    """Live run over local fixture models; ``router_reply(context)`` answers model_router."""
    providers = [
        ProviderConfig(
            name="fixture",
            model=name,
            base_url="http://localhost/" + name,
            retries=0,
            max_output_tokens=256,
            input_per_million=1.0 + position,
        )
        for position, name in enumerate(("cheap", "backup", "third")[:models])
    ]
    config = ResearchConfig(
        provider=providers[0],
        model_inventory=ModelInventory(
            models=[AvailableModel(id=p.model, label=p.model, provider=p) for p in providers]
        ),
    )
    config.pipeline.max_agent_repairs = 0
    if selection is not None:
        config.model_selection = selection
    seen: list[tuple[str, str]] = []
    prompts: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        role = ROUTER_ROLE if f"Metis role '{ROUTER_ROLE}'" in system else "other"
        seen.append((role, body["model"]))
        if role == ROUTER_ROLE:
            prompts.append(body["messages"][-1]["content"])
            reply = router_reply(json.loads(body["messages"][-1]["content"]))
            if isinstance(reply, int):
                return httpx.Response(reply, json={})
            # Low self-reported confidence does not void a validated route choice.
            output = AgentOutput(summary="Routes", confidence=0.3, structured={"routes": reply})
        else:
            output = AgentOutput(summary="Checked", confidence=1, limitations=["Synthetic"])
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": output.model_dump_json()}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(
        "autoresearch.agents.CompatibleProvider",
        lambda cfg: CompatibleProvider(
            cfg, client=httpx.Client(transport=httpx.MockTransport(transport))
        ),
    )

    def handler(state, config, runner):
        runner._one(state, "limitations", {}, 0)
        state.limitations = ["Synthetic limitation"]
        state.stage = (
            Stage.VERIFY_LIMITATIONS if state.stage == Stage.LIMITATIONS else Stage.LIMITATIONS
        )

    handler.behavior_identity = lambda: {"fixture": "model-selection-v1"}  # type: ignore[attr-defined]
    handlers = {Stage.LIMITATIONS: handler, Stage.VERIFY_LIMITATIONS: handler}
    store = Store(tmp_path / "state")
    state = Engine(store, config, stage_handlers=handlers).create(
        "Synthetic", "Private objective text"
    )
    return store, state, seen, prompts, handlers


def last_choice(context):
    return {
        role: {"primary": item["eligible"][-1], "fallbacks": [], "rationale": "Fixture choice."}
        for role, item in context["roles"].items()
    }


def kinds(store, run_id):
    return [event["kind"] for event in store.events(run_id)]


def test_creation_records_plan_without_any_model_call(tmp_path, monkeypatch):
    store, state, seen, _, _ = fixture_run(tmp_path, monkeypatch, last_choice)
    assert seen == []
    assert store.usage(state.id)["calls"] == 0
    assert "model_plan_created" in kinds(store, state.id)
    assert any(a["path"].endswith("model-plan.json") for a in store.artifacts(state.id))
    config = store.get_config(state.id)
    assert config.planned_routes["limitations"] == ["cheap", "backup", "third"]
    assert "refinement" not in store.get_run(state.id).model_plan


def test_router_runs_once_at_start_and_frozen_plan_drives_routing(tmp_path, monkeypatch):
    store, state, seen, prompts, handlers = fixture_run(tmp_path, monkeypatch, last_choice)
    first = Engine(store, stage_handlers=handlers).step(state.id)
    assert first.status == "ready", first.error
    # One accounted router call, then the stage call on the refined primary.
    assert seen == [(ROUTER_ROLE, "cheap"), ("other", "third")]
    assert "model_plan_refined" in kinds(store, state.id)
    assert first.model_plan["refinement"]["status"] == "applied"
    # Operational context: models and roles only, never research content.
    assert "Private objective text" not in prompts[0] and '"state"' not in prompts[0]
    # The stored configuration stays frozen; the sealed refinement is an execution view.
    frozen = store.get_config(state.id)
    assert frozen.planned_routes["limitations"][0] == "cheap"
    view = apply_model_plan(frozen, first, store)
    assert view.planned_routes["limitations"] == ["third", "cheap", "backup"]
    route = resolve_route(view, "limitations")
    assert route.provider.model == "third"
    alternatives = fallback_routes(view, route, role="limitations")
    assert [r.provider.model for r in alternatives] == ["third", "cheap", "backup"]
    # Later steps reuse the sealed plan without another router call.
    second = Engine(store, stage_handlers=handlers).step(state.id)
    assert second.status == "ready", second.error
    assert seen[2:] == [("other", "third")]
    assert kinds(store, state.id).count("model_plan_refined") == 1
    text = system_text(inspect_run(store, store.get_run(state.id)))
    assert "MODEL PLAN" in text and "model router, validated" in text
    # A tampered sealed refinement fails closed instead of silently changing routes.
    tampered = store.get_run(state.id)
    tampered.model_plan["refinement"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="changed"):
        apply_model_plan(store.get_config(state.id), tampered, store)


def test_invalid_router_choice_is_rejected_and_planner_plan_kept(tmp_path, monkeypatch):
    def outside(context):
        routes = last_choice(context)
        routes["limitations"]["primary"] = "invented-model"
        return routes

    store, state, seen, _, handlers = fixture_run(tmp_path, monkeypatch, outside)
    first = Engine(store, stage_handlers=handlers).step(state.id)
    assert first.status == "ready", first.error
    assert seen[-1] == ("other", "cheap")
    [event] = [e for e in store.events(state.id) if e["kind"] == "model_plan_router_rejected"]
    assert any("outside the eligible candidates" in v for v in event["payload"]["violations"])
    assert first.model_plan["refinement"]["status"] == "rejected"
    assert apply_model_plan(store.get_config(state.id), first, store) == store.get_config(state.id)


def test_router_provider_failure_keeps_planner_plan(tmp_path, monkeypatch):
    store, state, seen, _, handlers = fixture_run(tmp_path, monkeypatch, lambda _: 500)
    first = Engine(store, stage_handlers=handlers).step(state.id)
    assert first.status == "ready", first.error
    assert first.model_plan["refinement"]["status"] == "failed"
    assert "model_plan_router_failed" in kinds(store, state.id)
    assert seen[-1] == ("other", "cheap")
    # Failed router attempts are reserved and charged like any other call.
    assert store.usage(state.id)["calls"] >= 2


@pytest.mark.parametrize(
    ("selection", "models"), [(ModelSelectionConfig(router="off"), 3), (None, 1)]
)
def test_router_is_skipped_when_off_or_single_model(tmp_path, monkeypatch, selection, models):
    store, state, seen, _, handlers = fixture_run(
        tmp_path, monkeypatch, last_choice, selection=selection, models=models
    )
    assert Engine(store, stage_handlers=handlers).step(state.id).status == "ready"
    assert all(role != ROUTER_ROLE for role, _ in seen)
    assert "refinement" not in store.get_run(state.id).model_plan


def test_router_validation_rules():
    config = ResearchConfig(planned_routes={"limitations": ["a", "b"], "select": ["b"]})
    plan = {
        "roles": {
            "limitations": {"expected_calls": 1, "prompt_tokens": 10, "output_tokens": 10},
            "select": {"expected_calls": 1, "prompt_tokens": 10, "output_tokens": 10},
        },
        "models": {
            m: {
                "charge_input_per_million": 0,
                "charge_output_per_million": 0,
                "max_output_tokens": 100,
            }
            for m in ("a", "b")
        },
    }
    good = {
        "limitations": {"primary": "b", "fallbacks": ["a"], "rationale": "b first."},
        "select": {"primary": "b", "fallbacks": [], "rationale": "Only option."},
    }
    routes, rationale, violations = validate_routes(config, plan, good)
    assert violations == [] and routes["limitations"] == ["b", "a"]
    assert rationale["select"] == "Only option."
    for broken in (
        {**good, "select": {"primary": "b", "fallbacks": [], "rationale": ""}},
        {**good, "extra": {"primary": "a", "fallbacks": [], "rationale": "x"}},
        {"limitations": good["limitations"]},
        {**good, "limitations": {"primary": "a", "fallbacks": ["a"], "rationale": "dup"}},
    ):
        assert validate_routes(config, plan, broken)[2]
    plan["models"]["b"]["charge_input_per_million"] = 1e9
    assert "exceeds the run budget" in validate_routes(config, plan, good)[2][0]


# Observed outcomes --------------------------------------------------------------------


def test_outcomes_are_recorded_and_feed_the_planner(tmp_path, monkeypatch):
    provider = ProviderConfig(
        name="fixture", model="m", base_url="http://localhost/m", retries=0, max_output_tokens=256
    )
    config = ResearchConfig(provider=provider)
    config.pipeline.max_agent_repairs = 1
    store = Store(tmp_path / "state")
    state = RunState(id="0123456789ab", title="Synthetic", objective="Offline", created_at=now())
    store.create(state, config)
    replies = iter(
        [
            AgentOutput(summary="Missing payload"),
            AgentOutput(summary="Fixed", limitations=["Synthetic"]),
            None,
            429,
        ]
    )

    def transport(request):
        reply = next(replies)
        if reply is None:
            return httpx.Response(500, json={})
        if reply == 429:
            return httpx.Response(429, json={})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": reply.model_dump_json()}}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(
        "autoresearch.agents.CompatibleProvider",
        lambda cfg: CompatibleProvider(
            cfg, client=httpx.Client(transport=httpx.MockTransport(transport))
        ),
    )
    runner = AgentRunner(store, config)
    runner._one(state, "limitations", {}, 0)
    with pytest.raises(ProviderError):
        runner._one(state, "verify_limitations", {"note": "different request"}, 0)
    monkeypatch.setattr("autoresearch.providers.time.sleep", lambda _: None)
    with pytest.raises(ProviderError):
        runner._one(state, "select", {"note": "third request"}, 0)
    rows = store.model_outcome_rows()
    assert [(r["role"], r["outcome"], r["attempt"]) for r in rows] == [
        ("limitations", "schema_invalid", 0),
        ("limitations", "valid", 1),
        ("verify_limitations", "provider_failure", 0),
        ("select", "rate_limited", 0),
    ]
    stats = outcome_stats(rows)
    summary = stats["model"][quota_key(provider)]
    assert summary["samples"] == 4 and summary["provider_failures"] == 1
    assert summary["rate_limited"] == 1
    assert summary["first_try_valid"] == 0 and summary["repaired"] == 1
    # Enough poor outcomes push a model down a routine role's ranking.
    good, bad = (
        ProviderConfig(name="f", model=n, base_url=f"http://localhost/{n}") for n in ("good", "bad")
    )
    pool = ResearchConfig(
        provider=bad,
        model_inventory=ModelInventory(
            models=[AvailableModel(id=p.model, label=p.model, provider=p) for p in (bad, good)]
        ),
    )
    poor = [
        {
            "role": "limitations",
            "model": quota_key(bad),
            "outcome": "provider_failure",
            "attempt": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_seconds": 0,
            "cost_usd": 0,
        }
    ] * 6
    _, baseline = plan_and_prepare(pool)
    _, observed = plan_and_prepare(pool, stats=outcome_stats(poor))
    assert baseline["roles"]["limitations"]["primary"] == "bad"  # configured primary
    assert observed["roles"]["limitations"]["primary"] == "good"
    assert "6 provider failures" in observed["roles"]["limitations"]["observed"]["bad"]


def test_selection_policy_rejects_unknown_roles(tmp_path):
    root = copied_catalog(tmp_path)
    path = root / "policies/models.json"
    document = json.loads(path.read_text())
    document["selection"]["routine_roles"].append("invented_role")
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="unknown agents"):
        load_catalog(root)


def test_router_agent_contract_is_operational():
    catalog = load_catalog()
    agent = catalog.definition(ROUTER_ROLE)
    assert agent.context_policy == "operational" and not agent.tools
    assert "eligible" in catalog.render(ROUTER_ROLE)
    policy = catalog.models.selection
    assert policy is not None and ROUTER_ROLE in policy.routine_roles
    from autoresearch.model_profiles import FLASH_ROLES

    # Routine roles extend the existing economical-role policy; native slots stay fixed.
    assert set(FLASH_ROLES) - {"writing_writer"} <= set(policy.routine_roles)


def test_unplanned_role_keeps_cost_order_fallbacks():
    providers = [
        ProviderConfig(model=n, base_url=f"http://localhost/{n}", input_per_million=float(i))
        for i, n in enumerate(("a", "b", "c"))
    ]
    config = ResearchConfig(
        provider=providers[0],
        model_inventory=ModelInventory(
            models=[AvailableModel(id=p.model, label=p.model, provider=p) for p in providers]
        ),
        planned_routes={"limitations": ["c", "a"]},
    )
    route = ResolvedRoute(providers[2], "role_provider")
    planned = fallback_routes(config, route, role="limitations")
    assert [r.provider.model for r in planned] == ["c", "a"]
    unplanned = fallback_routes(config, ResolvedRoute(providers[0], "default"), role="select")
    assert [r.provider.model for r in unplanned] == ["a", "b", "c"]
    skipped = fallback_routes(
        config, route, {("http://localhost/a", "a", "XAI_API_KEY")}, role="limitations"
    )
    assert [r.provider.model for r in skipped] == ["c"]


def test_sealed_plan_is_outside_model_facing_state():
    from autoresearch.memory import research_view

    state = RunState(id="0123456789ab", title="Synthetic", objective="Offline")
    before = research_view(state)
    state.model_plan = {"planner": {"artifact_id": "x", "sha256": "y"}}
    assert research_view(state) == before and "model_plan" not in before
