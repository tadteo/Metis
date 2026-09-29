"""Compatibility entry point for the external, validated prompt specification layer."""

from .catalog import AgentCatalog, load_catalog


def system_prompt(role: str, override: str = "", catalog: AgentCatalog | None = None) -> str:
    return (catalog or load_catalog()).render(role, override)
