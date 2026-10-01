"""Pure provider selection from the inspected catalog and saved run configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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


def fallback_routes(config: ResearchConfig, route: ResolvedRoute) -> list[ResolvedRoute]:
    """At most two alternatives from the frozen permission pool; no access discovery."""
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
    for entry in sorted(
        eligible,
        key=lambda item: (
            item.provider.input_per_million + item.provider.output_per_million,
            item.id,
        ),
    ):
        if identity(entry.provider) not in seen:
            seen.add(identity(entry.provider))
            routes.append(ResolvedRoute(entry.provider.model_copy(deep=True), "provider_fallback"))
        if len(routes) == 3:
            break
    return routes
