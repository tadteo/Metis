"""Pure provider selection from the inspected catalog and saved run configuration."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .catalog import AgentCatalog, load_catalog
from .contracts import ProviderConfig

if TYPE_CHECKING:
    from .config import ResearchConfig


@dataclass(frozen=True)
class ResolvedRoute:
    provider: ProviderConfig
    reason: str


def resolve_route(
    config: ResearchConfig,
    role: str,
    index: int = 0,
    original_role: str | None = None,
    frontier: bool = False,
    catalog: AgentCatalog | None = None,
) -> ResolvedRoute:
    catalog = catalog or load_catalog()
    definition = catalog.definition(role)
    if index < 0:
        raise ValueError("panel index must be nonnegative")
    if definition.model_policy == "laya":
        if (
            role in config.role_providers
            or role in config.role_panels
            or role in config.role_commands
        ):
            raise ValueError(f"{role}: configure the typed model through ResearchConfig.laya")
        typed = config.laya
        return ResolvedRoute(
            ProviderConfig(
                name="laya",
                base_url=typed.base_url,
                model=typed.model,
                api_key_env=typed.api_key_env,
                timeout_seconds=typed.timeout_seconds,
                input_per_million=0,
                output_per_million=0,
                long_input_per_million=0,
                long_output_per_million=0,
                retries=0,
            ),
            "laya_typed_decision",
        )
    inherited = original_role if definition.model_policy == "inherit" else None
    if inherited:
        catalog.definition(inherited)
    for rule in catalog.models.precedence:
        provider = None
        if rule == "frontier" and frontier:
            provider = config.frontier_provider
        elif rule == "heldout" and definition.model_policy == "heldout":
            provider = config.heldout_provider
        elif rule == "role_panel" and config.role_panels.get(role):
            panel = config.role_panels[role]
            provider = panel[index % len(panel)]
        elif rule == "original_role_panel" and inherited and config.role_panels.get(inherited):
            panel = config.role_panels[inherited]
            provider = panel[index % len(panel)]
        elif rule == "original_role_provider" and inherited:
            provider = config.role_providers.get(inherited)
        elif rule == "role_provider":
            provider = config.role_providers.get(role)
        elif rule == "cheap" and definition.model_policy == "cheap":
            provider = config.cheap_provider
        elif rule == "default":
            provider = config.provider
        if provider is not None:
            return ResolvedRoute(provider.model_copy(deep=True), rule)
    raise ValueError("model routing has no default")


def fallback_routes(
    config: ResearchConfig,
    route: ResolvedRoute,
    unavailable: Collection[tuple[str, str, str]] = (),
    *,
    role: str | None = None,
) -> list[ResolvedRoute]:
    """At most two alternatives from the frozen permission pool; no access discovery.

    Models in ``unavailable`` (long-window quota exhausted) do not occupy an
    alternative slot; the next eligible model takes it. A role with a frozen model
    plan (``config.planned_routes``) uses only its planned models in plan order;
    other roles use the pool in cost order. The configured route always comes
    first so callers can report why it was skipped.
    """
    from .model_inventory import identity

    if config.model_inventory is None:
        return [route]
    eligible = [
        entry
        for entry in config.model_inventory.models
        if entry.enabled and (config.allowed_models is None or entry.id in config.allowed_models)
    ]
    if identity(route.provider) not in {identity(entry.provider) for entry in eligible}:
        raise ValueError("Configured route is outside the saved permitted model pool")
    routes = [route]
    seen = {identity(route.provider)}
    planned = (config.planned_routes or {}).get(role or "")
    if planned:
        by_id = {entry.id: entry for entry in eligible}
        ordered = [by_id[model_id] for model_id in planned if model_id in by_id]
    else:
        ordered = sorted(
            eligible,
            key=lambda item: (
                item.provider.input_per_million + item.provider.output_per_million,
                item.id,
            ),
        )
    for entry in ordered:
        if identity(entry.provider) not in seen and identity(entry.provider) not in unavailable:
            seen.add(identity(entry.provider))
            routes.append(ResolvedRoute(entry.provider.model_copy(deep=True), "provider_fallback"))
        if len(routes) == 3:
            break
    return routes


@dataclass(frozen=True)
class ModelLimits:
    context_window_tokens: int | None = None
    tokens_per_minute: int | None = None


_CONTEXT_FIELDS = ("context_window_tokens", "context_window", "max_input_tokens")
_TPM_FIELDS = ("tokens_per_minute", "input_tokens_per_minute", "tpm")


def _positive(source: Any, names: tuple[str, ...]) -> int | None:
    for name in names:
        value = source.get(name) if isinstance(source, Mapping) else getattr(source, name, None)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def model_limits(config: ResearchConfig, provider: ProviderConfig) -> ModelLimits:
    """Optional per-model token limits, read defensively.

    Interface (all optional; absent means "unknown, do not guard"): positive integer
    ``context_window_tokens`` and ``tokens_per_minute`` on the provider configuration
    or on its inventory entry, directly or under a ``limits`` mapping/object. Aliases
    in ``_CONTEXT_FIELDS``/``_TPM_FIELDS`` are accepted. The first value found wins.
    """
    from .model_inventory import identity

    sources: list[Any] = [provider]
    if config.model_inventory is not None:
        sources += [
            entry
            for entry in config.model_inventory.models
            if identity(entry.provider) == identity(provider)
        ]
    expanded: list[Any] = []
    for source in sources:
        expanded.append(source)
        limits = (
            source.get("limits") if isinstance(source, Mapping) else getattr(source, "limits", None)
        )
        if limits is not None:
            expanded.append(limits)
    context = next((v for s in expanded if (v := _positive(s, _CONTEXT_FIELDS))), None)
    tpm = next((v for s in expanded if (v := _positive(s, _TPM_FIELDS))), None)
    return ModelLimits(context, tpm)
