"""Automatic per-role model selection: a deterministic planner plus a validated agent step.

The planner performs no model or network call. It runs wherever ``prepare_models`` runs
(run creation, ``metis check``, the setup preview) and freezes per-role routes into the
run configuration. The optional ``model_router`` agent runs once after Start; it may only
choose among the planner's eligible models, and a deterministic validator falls back to
the planner's plan on any violation. Capability tiers are provider-published claims and
observed outcomes are operational records; neither is a research-quality measurement.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .catalog import AgentCatalog, CallEstimate, SelectionPolicy, load_catalog
from .contracts import ProviderConfig, RunState

if TYPE_CHECKING:
    from .agents import AgentRunner
    from .config import ModelSelectionConfig, ResearchConfig
    from .model_inventory import AvailableModel
    from .store import Store

PLAN_SCHEMA = 1
ROUTER_ROLE = "model_router"
MAX_FALLBACKS = 2
TIER_RANK = {"frontier": 4, "strong": 3, "standard": 2, "unknown": 2, "light": 1}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
FIXED_REASONS = {
    "inherit": "uses the calling role's route",
    "heldout": "held-out evaluator keeps its fixed route",
    "laya": "System 1 typed advice is configured separately",
    "writer": "native manuscript writer keeps its upstream model slots",
    "command": "external command adapter",
    "panel": "explicit panel keeps its configured models",
    "override": "explicit role override",
}


def selection_settings(config: ResearchConfig) -> ModelSelectionConfig:
    from .config import ModelSelectionConfig

    return config.model_selection or ModelSelectionConfig()


def _catalog(config: ResearchConfig) -> AgentCatalog:
    return load_catalog(Path(config.specification_dir) if config.specification_dir else None)


# ---------------------------------------------------------------- model facts


def _value(item: Any) -> Any:
    return getattr(item, "value", None) if item is not None else None


def model_facts(entry: AvailableModel) -> dict[str, Any]:
    """Selection-relevant metadata for one inventory entry; unknown values stay None."""
    provider = entry.provider
    preset = entry.preset
    limits = entry.limits
    local = urlsplit(provider.base_url).hostname in LOCAL_HOSTS
    capability = preset.model.capability if preset else None
    plan = "paid"
    if local or (preset is not None and not preset.key_required):
        plan = "local"
    elif preset is not None and preset.tier == "free":
        tier = preset.model.free_tier
        available = _value(tier.available) if tier else None
        published = tier is not None and any(
            getattr(tier, key) is not None
            for key in (
                "requests_per_minute",
                "requests_per_day",
                "tokens_per_minute",
                "tokens_per_day",
                "tokens_per_hour",
            )
        )
        if available is False:
            plan = "unavailable"
        elif available or published:
            plan = "free"
    cash = (0.0, 0.0) if plan in {"free", "local"} else None
    from .routing import model_limits as routing_limits

    def limit(name: str) -> int | float | None:
        return getattr(limits, name, None) if limits is not None else None

    requests_day = [
        v for v in (limit("requests_per_day"), _times(limit("requests_per_hour"), 24)) if v
    ]
    tokens_day = [
        v
        for v in (
            limit("tokens_per_day"),
            _times(limit("tokens_per_hour"), 24),
            _times(limit("tokens_per_month"), 1 / 30),
        )
        if v
    ]
    context = limit("context_window_tokens")
    tpm = limit("tokens_per_minute")
    if context is None or tpm is None:
        # Provider-level metadata (or aliases) without an inventory limits object.
        from .config import ResearchConfig

        fallback = routing_limits(ResearchConfig(provider=provider), provider)
        context = context or fallback.context_window_tokens
        tpm = tpm or fallback.tokens_per_minute
    observed_rpd = (
        preset is not None
        and preset.model.free_tier is not None
        and preset.model.free_tier.requests_per_day is not None
        and preset.model.free_tier.requests_per_day.basis == "observed"
    )
    from .model_inventory import identity

    return {
        "id": entry.id,
        "identity": "|".join(identity(provider)),
        "label": entry.label,
        "provider": provider.name,
        "model": provider.model,
        "plan": plan,
        "tier": capability.tier if capability else "unknown",
        "capability_note": capability.note if capability else None,
        "capability_source": capability.source_url if capability else None,
        "capability_basis": "provider-published, not measured by Metis" if capability else None,
        "list_input_per_million": provider.input_per_million,
        "list_output_per_million": provider.output_per_million,
        "charge_input_per_million": cash[0] if cash else provider.input_per_million,
        "charge_output_per_million": cash[1] if cash else provider.output_per_million,
        "context_window_tokens": context,
        "tokens_per_minute": tpm,
        "max_output_tokens": provider.max_output_tokens,
        "requests_per_day": int(min(requests_day)) if requests_day else None,
        "requests_per_day_basis": "observed" if observed_rpd else "published",
        "tokens_per_day": int(min(tokens_day)) if tokens_day else None,
        "requests_per_minute": limit("requests_per_minute"),
        "json_mode": provider.json_mode,
        "data_use": preset.data_use.text
        if preset is not None and preset.data_use is not None
        else None,
        "catalog_version": preset.catalog_version.isoformat() if preset else None,
    }


def _times(value: int | float | None, factor: float) -> float | None:
    return value * factor if value else None


# ---------------------------------------------------------------- observed outcomes


def outcome_stats(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate private per-attempt rows into per (role, model) and per model summaries."""
    groups: dict[str, dict[str, list[Mapping[str, Any]]]] = {"role": {}, "model": {}, "prompt": {}}
    for row in rows:
        groups["role"].setdefault(f"{row['role']}|{row['model']}", []).append(row)
        groups["model"].setdefault(str(row["model"]), []).append(row)
        groups["prompt"].setdefault(str(row["role"]), []).append(row)

    def summary(items: list[Mapping[str, Any]]) -> dict[str, Any]:
        responses = [r for r in items if r["outcome"] in {"valid", "schema_invalid"}]
        first = [r for r in responses if r["attempt"] == 0]
        failures = sum(r["outcome"] == "provider_failure" for r in items)
        return {
            "samples": len(items),
            "responses": len(responses),
            "first_try_valid": sum(r["outcome"] == "valid" for r in first),
            "first_attempts": len(first),
            "repaired": sum(r["outcome"] == "valid" and r["attempt"] > 0 for r in responses),
            "schema_invalid": sum(r["outcome"] == "schema_invalid" for r in responses),
            "provider_failures": failures,
            # Quota limits (HTTP 429) are shown but never count as model failures.
            "rate_limited": sum(r["outcome"] == "rate_limited" for r in items),
            "mean_latency_seconds": round(
                sum(float(r["latency_seconds"]) for r in responses) / len(responses), 2
            )
            if responses
            else None,
            "mean_cost_usd": round(sum(float(r["cost_usd"]) for r in items) / len(items), 6)
            if items
            else None,
        }

    prompt = {}
    for role, items in groups["prompt"].items():
        sizes = sorted(int(r["input_tokens"]) for r in items if int(r["input_tokens"]) > 0)
        if sizes:
            prompt[role] = {
                "samples": len(sizes),
                "p90_input_tokens": sizes[min(len(sizes) - 1, math.ceil(0.9 * len(sizes)) - 1)],
            }
    return {
        "role_model": {key: summary(items) for key, items in sorted(groups["role"].items())},
        "model": {key: summary(items) for key, items in sorted(groups["model"].items())},
        "prompt": prompt,
    }


def _failure_bucket(stats: Mapping[str, Any] | None, minimum: int) -> tuple[float, str]:
    if not stats or stats["samples"] < minimum:
        return 0.0, "no observed signal"
    attempts = stats["samples"] - stats.get("rate_limited", 0)
    if attempts < minimum:
        return 0.0, "no observed signal"
    failure = stats["provider_failures"] / attempts
    invalid = 1 - (
        stats["first_try_valid"] / stats["first_attempts"] if stats["first_attempts"] else 1
    )
    score = failure + invalid / 2
    text = (
        f"observed over {stats['samples']} attempts: "
        f"{stats['first_try_valid']}/{stats['first_attempts']} schema-valid first try, "
        f"{stats['provider_failures']} provider failures"
    )
    return round(score * 4) / 4, text


# ---------------------------------------------------------------- role needs


def _resolve(config: ResearchConfig, path: str) -> float:
    value: Any = config
    for part in path.split("."):
        value = getattr(value, part)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"model selection call estimate uses a non-numeric setting: {path}")
    return float(value)


def expected_calls(config: ResearchConfig, estimate: CallEstimate) -> float:
    result = estimate.factor
    for path in estimate.times:
        result *= _resolve(config, path)
    return round(result, 1)


def routable_roles(
    config: ResearchConfig, catalog: AgentCatalog, *, router: bool = True
) -> tuple[list[str], dict[str, str]]:
    """Roles the planner routes and roles that keep fixed routes (with the reason)."""
    from .workflow import get_workflow

    used = {role for node in get_workflow().nodes.values() for role in node.agents}
    if router and ROUTER_ROLE in catalog.agents:
        used.add(ROUTER_ROLE)
    planned: list[str] = []
    fixed: dict[str, str] = {}
    for role in sorted(used):
        definition = catalog.definition(role)
        if definition.model_policy in {"inherit", "heldout", "laya"}:
            fixed[role] = FIXED_REASONS[definition.model_policy]
        elif definition.context_policy == "heldout":
            fixed[role] = FIXED_REASONS["heldout"]
        elif definition.handler == "writer":
            fixed[role] = FIXED_REASONS["writer"]
        elif role in config.role_commands:
            fixed[role] = FIXED_REASONS["command"]
        elif role in config.role_panels:
            fixed[role] = FIXED_REASONS["panel"]
        elif role in config.role_providers:
            fixed[role] = FIXED_REASONS["override"]
        else:
            planned.append(role)
    return planned, fixed


def role_need(
    config: ResearchConfig,
    catalog: AgentCatalog,
    policy: SelectionPolicy,
    role: str,
    stats: Mapping[str, Any],
) -> dict[str, Any]:
    definition = catalog.definition(role)
    routine = definition.model_policy == "cheap" or role in policy.routine_roles
    observed = stats.get("prompt", {}).get(role)
    if observed and observed["samples"] >= policy.observed_min_samples:
        prompt = int(observed["p90_input_tokens"])
        basis = f"observed p90 over {observed['samples']} calls"
    else:
        prompt = policy.role_prompt_tokens.get(
            role,
            policy.prompt_tokens.get(definition.handler, policy.prompt_tokens.get("panel", 12000)),
        )
        basis = "policy estimate"
    return {
        "class": "routine" if routine else "critical",
        # Critical roles, and routine roles that must be capable (the router), keep the floor.
        "floor": not routine or role in policy.capable_routine_roles,
        "purpose": definition.purpose,
        "expected_calls": expected_calls(config, policy.calls.get(role, policy.default_calls)),
        "prompt_tokens": prompt,
        "prompt_basis": basis,
        "output_tokens": policy.output_tokens.get(definition.handler, 3000),
    }


# ---------------------------------------------------------------- planner


def _per_call(facts: Mapping[str, Any], prompt: int, output: int, prefix: str) -> float:
    return (
        float(
            prompt * facts[f"{prefix}_input_per_million"]
            + output * facts[f"{prefix}_output_per_million"]
        )
        / 1e6
    )


def exclusions(
    facts: Mapping[str, Any],
    need: Mapping[str, Any],
    policy: SelectionPolicy,
    settings: ModelSelectionConfig,
    *,
    sizes: bool = True,
) -> list[str]:
    """Hard-constraint violations for one model and role (empty means eligible).

    ``sizes=False`` ignores the context and tokens/minute estimates (used only when no
    model fits them; the request-size guard then decides each call).
    """
    reasons = []
    output = min(need["output_tokens"], facts["max_output_tokens"])
    prompt = need["prompt_tokens"]
    if facts["plan"] == "unavailable":
        reasons.append("not offered on the free tier")
    if settings.exclude_data_use_caveats and facts["plan"] == "free" and facts["data_use"]:
        reasons.append("free tier with a data-use caveat (excluded by setting)")
    if policy.json_required and not facts["json_mode"]:
        reasons.append("no JSON mode")
    context = facts["context_window_tokens"] if sizes else None
    needed = math.ceil(prompt * policy.context_margin) + output
    if context and needed > context:
        reasons.append(f"context window {context:,} < {needed:,} tokens needed")
    tpm = facts["tokens_per_minute"] if sizes else None
    if tpm and prompt + output > tpm:
        reasons.append(f"tokens/minute {tpm:,} < {prompt + output:,} per request")
    if need["floor"] and TIER_RANK[facts["tier"]] < TIER_RANK[policy.critical_floor]:
        reasons.append(f"provider tier '{facts['tier']}' below the critical floor")
    return reasons


def _key(
    facts: Mapping[str, Any], need: Mapping[str, Any], primary_id: str, penalty: float
) -> tuple[Any, ...]:
    output = min(need["output_tokens"], facts["max_output_tokens"])
    charge = _per_call(facts, need["prompt_tokens"], output, "charge")
    listed = _per_call(facts, need["prompt_tokens"], output, "list")
    rank = TIER_RANK[facts["tier"]]
    not_primary = facts["id"] != primary_id
    if need["class"] == "critical":
        band: tuple[Any, ...] = (-rank, charge > 0, penalty)
        tail: tuple[Any, ...] = (not_primary, charge, listed, facts["id"])
    else:
        band = (charge > 0, round(charge, 6), penalty)
        tail = (-rank, not_primary, listed, facts["id"])
    return band + tail


def _days(load: Mapping[str, float], facts: Mapping[str, Any]) -> float | None:
    values = []
    if facts["requests_per_day"]:
        values.append(load["calls"] / facts["requests_per_day"])
    if facts["tokens_per_day"]:
        values.append(load["tokens"] / facts["tokens_per_day"])
    return max(values) if values else None


def plan_models(
    config: ResearchConfig,
    candidates: list[AvailableModel],
    primary_id: str,
    *,
    stats: Mapping[str, Any] | None = None,
    catalog: AgentCatalog | None = None,
) -> dict[str, Any] | None:
    """Deterministic per-role plan over the usable permitted pool. No model calls."""
    catalog = catalog or _catalog(config)
    policy = catalog.models.selection
    settings = selection_settings(config)
    if policy is None or not settings.enabled or not candidates:
        return None
    if config.planned_routes is not None:
        # A frozen run configuration: its recorded plan is authoritative; never re-plan.
        return None
    stats = dict(stats or {})
    facts = {entry.id: model_facts(entry) for entry in candidates}
    router = settings.router == "on" or (settings.router == "auto" and len(candidates) >= 2)
    planned, fixed = routable_roles(config, catalog, router=router)
    if not planned:
        return None
    needs = {role: role_need(config, catalog, policy, role, stats) for role in planned}
    load = {model_id: {"calls": 0.0, "tokens": 0.0} for model_id in facts}
    roles: dict[str, Any] = {}
    warnings: list[str] = []
    budget = config.budget.usd
    charged = 0.0
    order = sorted(
        planned,
        key=lambda r: (
            needs[r]["class"] != "critical",
            -needs[r]["expected_calls"] * (needs[r]["prompt_tokens"] + needs[r]["output_tokens"]),
            r,
        ),
    )
    for role in order:
        need = needs[role]
        excluded = {}
        ranked = []
        for model_id, item in facts.items():
            reasons = exclusions(item, need, policy, settings)
            if reasons:
                excluded[model_id] = reasons
                continue
            role_stats = stats.get("role_model", {}).get(f"{role}|{_model_key(item)}")
            model_stats = stats.get("model", {}).get(_model_key(item))
            usable = (
                role_stats
                if role_stats and role_stats["samples"] >= policy.observed_min_samples
                else model_stats
            )
            penalty, observed = _failure_bucket(usable, policy.observed_min_samples)
            ranked.append((_key(item, need, primary_id, penalty), model_id, observed))
        relaxed = False
        if not ranked:
            # No model fits the size estimates: keep every other constraint (never drop
            # the capability floor) and let the request-size guard decide each call.
            for model_id, item in facts.items():
                if not exclusions(item, need, policy, settings, sizes=False):
                    ranked.append(
                        (_key(item, need, primary_id, 0.0), model_id, "no observed signal")
                    )
            relaxed = bool(ranked)
        ranked.sort()
        if not ranked:
            primary_reasons = exclusions(facts[primary_id], need, policy, settings, sizes=False)
            if any("data-use caveat" in r for r in primary_reasons):
                raise ValueError(
                    f"Every permitted model for the {role} role is excluded by the data-use "
                    "setting or other limits. Add a model without that caveat or change "
                    "model_selection.exclude_data_use_caveats."
                )
            if need["floor"] and any("critical floor" in r for r in primary_reasons):
                raise ValueError(
                    f"No permitted model meets the capability floor for the "
                    f"{need['class']} role {role}. Add a stronger model in Settings or "
                    "adjust project permissions."
                )
            warnings.append(
                f"{role}: no permitted model meets its constraints; it uses the primary "
                "model and the request-size guard decides each call."
            )
            choice = [primary_id]
            reason = "no model satisfies the constraints; primary model retained"
            observed_text = {primary_id: "no observed signal"}
        else:
            if relaxed:
                warnings.append(
                    f"{role}: no permitted model fits the estimated request size; the "
                    "request-size guard decides each call."
                )
            bands: list[list[tuple[Any, ...]]] = []
            for candidate in ranked:
                if bands and bands[-1][0][0][:3] == candidate[0][:3]:
                    bands[-1].append(candidate)
                else:
                    bands.append([candidate])
            # Critical work may spill only to equally capable models (e.g. a paid plan);
            # routine work may spill to the next cheapest band.
            allowed = [
                group
                for group in bands
                if need["class"] != "critical" or group[0][0][0] == bands[0][0][0][0]
            ]
            current = max([d for m in facts if (d := _days(load[m], facts[m]))] or [0.0])
            target = max(1.0, current)
            tokens = need["expected_calls"] * (need["prompt_tokens"] + need["output_tokens"])

            def projected(
                model_id: str, calls: float = need["expected_calls"], tokens: float = tokens
            ) -> float:
                after = {
                    "calls": load[model_id]["calls"] + calls,
                    "tokens": load[model_id]["tokens"] + tokens,
                }
                return _days(after, facts[model_id]) or 0.0

            def role_charge(model_id: str, need: Mapping[str, Any] = need) -> float:
                output = min(need["output_tokens"], facts[model_id]["max_output_tokens"])
                return float(need["expected_calls"]) * _per_call(
                    facts[model_id], need["prompt_tokens"], output, "charge"
                )

            best = None
            spilled = False
            for position, group in enumerate(allowed):
                fitting = [
                    item
                    for item in group
                    if projected(item[1]) <= target
                    # Spill to a charged band only while the run budget allows it.
                    and (position == 0 or charged + role_charge(item[1]) <= budget)
                ]
                if fitting:
                    # Free quotas are shared scarce resources: balance them. Paid and
                    # local models keep preference order (configured primary first).
                    best = min(
                        fitting,
                        key=lambda item: (
                            load[item[1]]["calls"] if facts[item[1]]["plan"] == "free" else 0,
                            item[0],
                        ),
                    )
                    spilled = position > 0
                    break
            if best is None:
                best = min(bands[0], key=lambda item: (projected(item[1]), item[0]))
            primary = best[1]
            band_of = {item[1]: item[0][:3] for item in ranked}
            rest = [item[1] for item in ranked if item[1] != primary]
            # Within a band, a fallback from another provider first: separate quota pools.
            rest.sort(
                key=lambda m: (band_of[m], facts[m]["provider"] == facts[primary]["provider"])
            )
            choice = [primary, *rest]
            reason = _why(
                facts[primary],
                need,
                sum(facts[item[1]]["plan"] == "free" for item in bands[0]),
                spilled,
                best not in [i for g in allowed for i in g if projected(i[1]) <= target],
            )
            if relaxed:
                reason += "; no model fits the estimated request size"
            observed_text = {item[1]: item[2] for item in ranked}
        output = min(need["output_tokens"], facts[choice[0]]["max_output_tokens"])
        charged += need["expected_calls"] * _per_call(
            facts[choice[0]], need["prompt_tokens"], output, "charge"
        )
        load[choice[0]]["calls"] += need["expected_calls"]
        load[choice[0]]["tokens"] += need["expected_calls"] * (
            need["prompt_tokens"] + need["output_tokens"]
        )
        output = min(need["output_tokens"], facts[choice[0]]["max_output_tokens"])
        roles[role] = {
            **need,
            "primary": choice[0],
            "fallbacks": choice[1 : 1 + MAX_FALLBACKS],
            "eligible": choice if ranked else [],
            "excluded": excluded,
            "observed": observed_text,
            "why": reason,
            "estimated_charge_usd": round(
                need["expected_calls"]
                * _per_call(facts[choice[0]], need["prompt_tokens"], output, "charge"),
                4,
            ),
            "estimated_list_cost_usd": round(
                need["expected_calls"]
                * _per_call(facts[choice[0]], need["prompt_tokens"], output, "list"),
                4,
            ),
        }
    plan = {
        "schema_version": PLAN_SCHEMA,
        "planner": "deterministic",
        "policy_version": policy.version,
        "settings": settings.model_dump(mode="json"),
        "configured_primary": primary_id,
        "models": facts,
        "roles": {role: roles[role] for role in sorted(roles)},
        "fixed_roles": fixed,
        "observed_outcomes": _pool_outcomes(stats, facts, planned),
        "warnings": warnings,
        "note": "Estimates from configuration and provider-published figures; capability "
        "tiers are provider claims and observed outcomes are operational records, not "
        "measured research quality.",
    }
    summary = totals(plan)
    plan["totals"] = summary
    if summary["estimated_charge_usd"] > budget:
        warnings.append(
            f"The expected charge ${summary['estimated_charge_usd']:.2f} exceeds the run "
            f"budget ${budget:.2f}; the run stops when the budget is spent. Raise the budget "
            "or remove paid models."
        )
    return plan


def _pool_outcomes(
    stats: Mapping[str, Any], facts: Mapping[str, Any], roles: list[str]
) -> dict[str, Any]:
    """Outcome summaries for this pool and these roles only, keyed by inventory ID."""
    ids = {item["identity"]: model_id for model_id, item in facts.items()}
    role_model = {}
    for key, value in stats.get("role_model", {}).items():
        role, _, identity = key.partition("|")
        if role in roles and identity in ids:
            role_model[f"{role}|{ids[identity]}"] = value
    return {
        "role_model": role_model,
        "model": {ids[k]: v for k, v in stats.get("model", {}).items() if k in ids},
        "prompt": {k: v for k, v in stats.get("prompt", {}).items() if k in roles},
    }


def _model_key(facts: Mapping[str, Any]) -> str:
    return str(facts.get("identity", ""))


def _why(
    facts: Mapping[str, Any],
    need: Mapping[str, Any],
    free_in_band: int,
    spilled: bool,
    overloaded: bool,
) -> str:
    plan = {"free": "free tier", "local": "local server", "paid": "paid plan"}.get(
        facts["plan"], facts["plan"]
    )
    if need["class"] == "critical":
        text = f"critical role: highest eligible provider tier ({facts['tier']}), {plan}"
    else:
        text = f"routine role: lowest expected charge ({plan})"
    if spilled:
        text += "; preferred free quotas are already planned for a full day"
    elif overloaded:
        text += "; every eligible model is quota-bound, least-loaded chosen"
    elif free_in_band > 1:
        text += "; spread across equally ranked free models by quota load"
    return text


def totals(plan: Mapping[str, Any]) -> dict[str, Any]:
    facts = plan["models"]
    load: dict[str, dict[str, float]] = {}
    for role in plan["roles"].values():
        item = load.setdefault(role["primary"], {"calls": 0.0, "tokens": 0.0})
        item["calls"] += role["expected_calls"]
        item["tokens"] += role["expected_calls"] * (role["prompt_tokens"] + role["output_tokens"])
    per_model = {}
    unknown = []
    worst = None
    for model_id, item in sorted(load.items()):
        days = _days(item, facts[model_id]) if model_id in facts else None
        if days is None:
            unknown.append(model_id)
        elif worst is None or days > worst[0]:
            worst = (days, model_id)
        per_model[model_id] = {
            "expected_calls": round(item["calls"], 1),
            "expected_tokens": int(item["tokens"]),
            "requests_per_day": facts.get(model_id, {}).get("requests_per_day"),
            "tokens_per_day": facts.get(model_id, {}).get("tokens_per_day"),
            "days": round(days, 2) if days is not None else None,
        }
    return {
        "expected_calls": round(sum(r["expected_calls"] for r in plan["roles"].values()), 1),
        "estimated_charge_usd": round(
            sum(r["estimated_charge_usd"] for r in plan["roles"].values()), 2
        ),
        "estimated_list_cost_usd": round(
            sum(r["estimated_list_cost_usd"] for r in plan["roles"].values()), 2
        ),
        "days": max(1, math.ceil(worst[0])) if worst else None,
        "binding_model": worst[1] if worst and worst[0] > 1 else None,
        "models_without_published_daily_quota": unknown,
        "per_model": per_model,
    }


def plan_digest(plan: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def summary_text(plan: Mapping[str, Any]) -> str:
    """One readable paragraph for setup checks (CLI, TUI and browser share it)."""
    data = plan["totals"]
    models = plan["models"]
    counts: dict[str, list[str]] = {}
    for role in plan["roles"].values():
        counts.setdefault(role["primary"], []).append(role["class"])
    parts = [
        f"{models[m]['label']}: {len(c)} role{'s' if len(c) != 1 else ''}"
        + (f" ({c.count('critical')} critical)" if c.count("critical") else "")
        for m, c in sorted(counts.items(), key=lambda item: -len(item[1]))
    ]
    days = data["days"]
    quota = (
        f"published daily quotas allow this in about {days} day{'s' if days != 1 else ''}"
        if days
        else "no published daily quota applies"
    )
    if days and data["models_without_published_daily_quota"]:
        quota += " (models without a published daily quota are not counted)"
    text = (
        f"Automatic model plan (no model call): {'; '.join(parts)}. "
        f"About {data['expected_calls']:.0f} calls; expected charge "
        f"${data['estimated_charge_usd']:.2f} (list-price equivalent "
        f"${data['estimated_list_cost_usd']:.2f}); {quota}. Estimates, not measurements."
    )
    if plan["warnings"]:
        text += " " + " ".join(plan["warnings"])
    return text


def frozen_routes(plan: Mapping[str, Any]) -> dict[str, list[str]]:
    return {
        role: list(item["eligible"]) for role, item in plan["roles"].items() if item["eligible"]
    }


# ---------------------------------------------------------------- router step


def router_pending(config: ResearchConfig, state: RunState) -> bool:
    settings = selection_settings(config)
    return bool(
        config.mode == "live"
        and settings.enabled
        and settings.router != "off"
        and config.planned_routes
        and config.model_inventory is not None
        and ROUTER_ROLE not in config.role_commands
        and "planner" in state.model_plan
        and "refinement" not in state.model_plan
        and (settings.router == "on" or len(config.model_inventory.models) >= 2)
    )


def router_context(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Operational request: models and roles only, never research content."""
    roles = {
        role: {
            key: item[key]
            for key in (
                "class",
                "purpose",
                "expected_calls",
                "prompt_tokens",
                "output_tokens",
                "primary",
                "fallbacks",
                "eligible",
                "why",
            )
        }
        for role, item in plan["roles"].items()
        if item["eligible"]
    }
    return {
        "roles": roles,
        # No endpoints or key variable names: identity stays in the private plan.
        "models": {
            model_id: {k: v for k, v in item.items() if k != "identity"}
            for model_id, item in plan["models"].items()
        },
        "observed_outcomes": plan.get("observed_outcomes", {}),
        "totals": plan["totals"],
        "response_contract": {
            "structured": {
                "routes": {
                    "ROLE": {"primary": "MODEL_ID", "fallbacks": ["MODEL_ID"], "rationale": "TEXT"}
                }
            }
        },
    }


def validate_routes(
    config: ResearchConfig, plan: Mapping[str, Any], proposed: Any
) -> tuple[dict[str, list[str]], dict[str, str], list[str]]:
    """Deterministic acceptance of a router proposal. Any violation rejects the whole plan."""
    planned = config.planned_routes or {}
    violations: list[str] = []
    routes: dict[str, list[str]] = {}
    rationale: dict[str, str] = {}
    if not isinstance(proposed, dict):
        return {}, {}, ["routes must be an object keyed by role"]
    for role in sorted(set(proposed) - set(planned)):
        violations.append(f"{role}: not a planned role")
    for role, eligible in planned.items():
        item = proposed.get(role)
        if not isinstance(item, dict):
            violations.append(f"{role}: missing route")
            continue
        primary, fallbacks, text = (
            item.get("primary"),
            item.get("fallbacks", []),
            item.get("rationale"),
        )
        if not isinstance(fallbacks, list) or len(fallbacks) > MAX_FALLBACKS:
            violations.append(f"{role}: fallbacks must be a list of at most {MAX_FALLBACKS}")
            continue
        chosen = [primary, *fallbacks]
        if not all(isinstance(m, str) for m in chosen) or len(set(chosen)) != len(chosen):
            violations.append(f"{role}: model IDs must be distinct strings")
            continue
        outside = [m for m in chosen if m not in eligible]
        if outside:
            violations.append(f"{role}: {', '.join(outside)} outside the eligible candidates")
            continue
        if not isinstance(text, str) or not text.strip() or len(text) > 600:
            violations.append(f"{role}: a rationale (at most 600 characters) is required")
            continue
        routes[role] = chosen + [m for m in eligible if m not in chosen]
        rationale[role] = text.strip()
    if not violations:
        charge = 0.0
        for role, order in routes.items():
            need = plan["roles"][role]
            facts = plan["models"][order[0]]
            output = min(need["output_tokens"], facts["max_output_tokens"])
            charge += need["expected_calls"] * _per_call(
                facts, need["prompt_tokens"], output, "charge"
            )
        planner_charge = float(plan.get("totals", {}).get("estimated_charge_usd", 0.0))
        allowed_charge = max(config.budget.usd, planner_charge)
        if charge > allowed_charge + 1e-9:
            violations.append(
                f"expected charge ${charge:.2f} exceeds the run budget ${config.budget.usd:.2f}"
                + (" and the planner's estimate" if planner_charge > config.budget.usd else "")
            )
        if "totals" in plan:
            before = plan["totals"].get("days") or 1
            after = with_routes(plan, routes)["totals"].get("days") or 1
            if after > before:
                violations.append(
                    f"published daily quotas would need about {after} days instead of {before}"
                )
    return (routes, rationale, violations) if not violations else ({}, {}, violations)


def _read_json_artifact(store: Store, state: RunState, reference: Mapping[str, Any]) -> Any:
    content = store.artifact_content(state.id, str(reference["artifact_id"]))
    if hashlib.sha256(content).hexdigest() != reference["sha256"]:
        raise ValueError("Sealed model plan changed")
    return json.loads(content)


def record_plan(store: Store, state: RunState, plan: Mapping[str, Any]) -> None:
    """Archive the planner's plan at creation. Records only; never calls a model."""
    record = store.artifact(
        state.id, "model_plan", "model-plan.json", json.dumps(plan, indent=2, sort_keys=True)
    )
    state.model_plan = {
        "planner": {"artifact_id": record["id"], "sha256": record["sha256"]},
    }
    store.save(
        state,
        "model_plan_created",
        {
            "artifact": record["id"],
            "sha256": record["sha256"],
            "routes": {r: item["primary"] for r, item in plan["roles"].items()},
            "totals": {k: v for k, v in plan["totals"].items() if k != "per_model"},
            "warnings": plan["warnings"],
        },
    )


def refine_plan(store: Store, state: RunState, config: ResearchConfig, runner: AgentRunner) -> None:
    """One accounted router call after Start; any failure keeps the planner's plan."""
    from .providers import ProviderError

    plan = _read_json_artifact(store, state, state.model_plan["planner"])
    record: dict[str, Any] = {"planner_sha256": state.model_plan["planner"]["sha256"]}
    try:
        output = runner.run(state, ROUTER_ROLE, router_context(plan))
    except (ProviderError, ValueError) as error:
        from .privacy import redact

        reason = redact(f"{type(error).__name__}: {error}", config.privacy.redact_patterns)
        record.update(status="failed", reason=str(reason)[:2000])
    else:
        # The router's own answer: panel aggregation may downgrade a low self-reported
        # confidence to "refine", which carries no meaning for a validated route choice.
        panel = output.structured.get("panel_outputs") or [output.model_dump()]
        own = panel[0] if isinstance(panel[0], dict) else output.model_dump()
        structured = own.get("structured") or {}
        decision = own.get("decision", output.decision)
        record.update(
            router_output={
                "decision": decision,
                "confidence": own.get("confidence"),
                "summary": own.get("summary", output.summary),
                "structured": structured,
            }
        )
        if decision != "accept":
            record.update(status="declined", reason=own.get("feedback") or output.summary)
        else:
            routes, rationale, violations = validate_routes(config, plan, structured.get("routes"))
            if violations:
                record.update(status="rejected", violations=violations)
            else:
                record.update(status="applied", final_routes=routes, rationale=rationale)
    if record["status"] != "applied":
        record["final_routes"] = dict(config.planned_routes or {})
    artifact = store.artifact(
        state.id,
        "model_plan",
        "model-plan-refined.json",
        json.dumps(record, indent=2, sort_keys=True),
    )
    state.model_plan = {
        **state.model_plan,
        "refinement": {
            "status": record["status"],
            "artifact_id": artifact["id"],
            "sha256": artifact["sha256"],
        },
    }
    kind = {
        "applied": "model_plan_refined",
        "rejected": "model_plan_router_rejected",
    }.get(record["status"], "model_plan_router_failed")
    changed = {
        role: order[0]
        for role, order in record["final_routes"].items()
        if order[:1] != (config.planned_routes or {}).get(role, [])[:1]
    }
    store.save(
        state,
        kind,
        {
            "status": record["status"],
            "artifact": artifact["id"],
            "changed_primaries": changed,
            "violations": record.get("violations", []),
            "reason": record.get("reason", ""),
        },
    )


def apply_model_plan(config: ResearchConfig, state: RunState, store: Store) -> ResearchConfig:
    """Ephemeral execution view of a sealed, re-validated router refinement."""
    reference = state.model_plan.get("refinement")
    if not reference or reference.get("status") != "applied":
        return config
    record = _read_json_artifact(store, state, reference)
    if record.get("planner_sha256") != state.model_plan.get("planner", {}).get("sha256"):
        raise ValueError("Sealed model plan refines a different planner record")
    planned = config.planned_routes or {}
    entries = {m.id: m for m in (config.model_inventory.models if config.model_inventory else [])}
    result = config.model_copy(deep=True)
    routes = dict(planned)
    for role, order in record["final_routes"].items():
        if (
            role not in planned
            or not order
            or set(order) != set(planned[role])
            or len(order) != len(set(order))
        ):
            raise ValueError("Sealed model plan is outside the frozen eligible routes")
        result.role_providers[role] = entries[order[0]].provider.model_copy(deep=True)
        routes[role] = list(order)
    result.planned_routes = routes
    return result


def with_routes(plan: Mapping[str, Any], final: Mapping[str, list[str]]) -> dict[str, Any]:
    """The plan with refined orders, per-role estimates and totals recomputed."""
    result: dict[str, Any] = json.loads(json.dumps(plan))
    for role, order in final.items():
        item = result["roles"].get(role)
        if item is None or not order:
            continue
        facts = result["models"][order[0]]
        output = min(item["output_tokens"], facts["max_output_tokens"])
        item.update(primary=order[0], fallbacks=order[1 : 1 + MAX_FALLBACKS], eligible=order)
        for key, prefix in (
            ("estimated_charge_usd", "charge"),
            ("estimated_list_cost_usd", "list"),
        ):
            item[key] = round(
                item["expected_calls"] * _per_call(facts, item["prompt_tokens"], output, prefix), 4
            )
    result["totals"] = totals(result)
    return result


def preview(
    plan: Mapping[str, Any], rationale: Mapping[str, str] | None = None, source: str = "planner"
) -> dict[str, Any]:
    """Compact projection shared by setup checks and the AI system view."""
    rationale = rationale or {}
    rows = [
        {
            "role": role,
            "class": item["class"],
            "model": plan["models"][item["primary"]]["label"],
            "fallbacks": [plan["models"][m]["label"] for m in item["fallbacks"]],
            "why": rationale.get(role, item["why"]),
            "source": source if role in rationale or source == "planner" else "planner",
            "expected_calls": item["expected_calls"],
            "estimated_charge_usd": item["estimated_charge_usd"],
        }
        for role, item in plan["roles"].items()
    ]
    return {
        "summary": summary_text(plan),
        "totals": {k: v for k, v in plan["totals"].items() if k != "per_model"},
        "per_model": {
            plan["models"][m]["label"] if m in plan["models"] else m: value
            for m, value in plan["totals"]["per_model"].items()
        },
        "routes": rows,
        "fixed_roles": plan["fixed_roles"],
        "warnings": plan["warnings"],
    }


def plan_view(store: Store, state: RunState) -> dict[str, Any] | None:
    """Recorded plan for inspection surfaces: planner, refinement and final routes."""
    planner_ref = state.model_plan.get("planner")
    if not planner_ref:
        return None
    try:
        plan = _read_json_artifact(store, state, planner_ref)
        refinement = (
            _read_json_artifact(store, state, state.model_plan["refinement"])
            if state.model_plan.get("refinement")
            else None
        )
    except (OSError, ValueError, KeyError) as error:
        return {"status": "unreadable", "error": str(error)}
    if refinement is not None and refinement.get("status") == "applied":
        view = preview(
            with_routes(plan, refinement["final_routes"]), refinement["rationale"], "model router"
        )
    else:
        view = preview(plan)
    view["status"] = refinement["status"] if refinement else "planner"
    view["router"] = {
        key: refinement[key]
        for key in ("status", "reason", "violations")
        if refinement is not None and key in refinement
    }
    return view


def workhorse(plan: Mapping[str, Any]) -> str | None:
    """The model carrying the most expected critical calls, preferring models without a
    published daily quota: frontier escalation is a fixed route with no fallback."""
    calls: dict[str, float] = {}
    for item in plan["roles"].values():
        if item["class"] == "critical" and item["eligible"]:
            calls[item["primary"]] = calls.get(item["primary"], 0.0) + item["expected_calls"]

    def daily(model_id: str) -> bool:
        facts = plan["models"][model_id]
        return bool(facts["requests_per_day"] or facts["tokens_per_day"])

    return min(calls, key=lambda m: (daily(m), -calls[m], m)) if calls else None


def best_general(candidates: list[AvailableModel]) -> AvailableModel:
    """Primary when the configured one is unusable: most capable, then no charge, then cost."""

    def key(entry: AvailableModel) -> tuple[Any, ...]:
        facts = model_facts(entry)
        charge = facts["charge_input_per_million"] + facts["charge_output_per_million"]
        return (
            facts["plan"] == "unavailable",
            not facts["json_mode"],
            -TIER_RANK[facts["tier"]],
            charge > 0,
            charge,
            entry.id,
        )

    return min(candidates, key=key)


def provider_for(config: ResearchConfig, model_id: str) -> ProviderConfig:
    entries = config.model_inventory.models if config.model_inventory else []
    return next(m.provider for m in entries if m.id == model_id).model_copy(deep=True)
