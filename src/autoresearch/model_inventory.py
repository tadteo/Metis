"""Host-local access inspection and deterministic new-run model selection.

No network probes. Resolved routes are stored with the run, never recomputed on resume.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from .contracts import Model, ProviderConfig

if TYPE_CHECKING:
    from .config import ResearchConfig


class AvailableModel(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    label: str = Field(min_length=1, max_length=120)
    provider: ProviderConfig
    enabled: bool = True


class ModelInventory(Model):
    models: list[AvailableModel] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self) -> ModelInventory:
        if len({m.id for m in self.models}) != len(self.models):
            raise ValueError("Model IDs must be unique")
        if any(m.provider.name.lower() in {"laya", "system1", "system-one"} for m in self.models):
            raise ValueError("Configure System 1 separately through Laya settings")
        return self


def identity(provider: ProviderConfig) -> tuple[str, str, str]:
    return provider.base_url.rstrip("/"), provider.model, provider.api_key_env


def initial_inventory(config: ResearchConfig) -> ModelInventory:
    from .model_profiles import apply_model_profile

    providers = [config.provider]
    providers += [
        p for p in (config.cheap_provider, config.frontier_provider, config.heldout_provider) if p
    ]
    providers += list(config.role_providers.values())
    providers += [p for panel in config.role_panels.values() for p in panel]
    from .config import ResearchConfig

    flash = apply_model_profile(ResearchConfig(), "google-flash").cheap_provider
    if flash is not None:
        providers.append(flash)
    seen = set()
    entries = []
    for provider in providers:
        if provider is None or identity(provider) in seen:
            continue
        seen.add(identity(provider))
        key = hashlib.sha256("|".join(identity(provider)).encode()).hexdigest()[:16]
        entries.append(AvailableModel(id=key, label=provider.model, provider=provider))
    return ModelInventory(models=entries)


def access(entry: AvailableModel) -> dict[str, Any]:
    from .credentials import CredentialAccessError, resolve, valid_secret
    from .providers import CompatibleProvider, ProviderError

    base = {"id": entry.id, "usable": False, "status": "disabled", "source": "missing"}
    if not entry.enabled:
        return base
    try:
        CompatibleProvider(entry.provider)
        if not entry.provider.model.strip():
            raise ValueError("Model ID is required")
        key, source = resolve(entry.provider.api_key_env)
        local = urlsplit(entry.provider.base_url).hostname in {"localhost", "127.0.0.1", "::1"}
        if key and not valid_secret(key):
            return {**base, "status": "invalid_key", "source": source}
        return {
            **base,
            "usable": bool(key) or local,
            "status": "configured" if key or local else "key_needed",
            "source": source,
        }
    except (CredentialAccessError, ProviderError, ValueError):
        return {**base, "status": "unavailable"}


def inventory_status(config: ResearchConfig) -> list[dict[str, Any]]:
    inventory = config.model_inventory or initial_inventory(config)
    return [access(entry) for entry in inventory.models]


def prepare_models(config: ResearchConfig) -> ResearchConfig:
    """Compile inventory to existing explicit routes before freezing a new run."""
    if config.mode == "demo":
        return config.model_copy(deep=True)
    if config.model_inventory is None:
        if config.allowed_models is not None:
            raise ValueError("Project model permissions require a configured model inventory")
        return config.model_copy(deep=True)
    from .model_profiles import FLASH_ROLES

    result = config.model_copy(deep=True)
    entries = config.model_inventory.models
    if not any(identity(m.provider) == identity(config.provider) for m in entries):
        raise ValueError(
            "The primary model is outside the inventory. Configure it in Available to Metis or disable inventory for explicit routing."
        )
    allowed = config.allowed_models
    candidates = [
        m for m in entries if (allowed is None or m.id in allowed) and access(m)["usable"]
    ]
    if not candidates:
        raise ValueError(
            "No configured model is available within this project's model permissions. Open Settings to connect or allow a model."
        )
    if allowed is not None and config.role_commands:
        raise ValueError(
            "Project model restrictions cannot verify external role commands. Remove the commands or use an unrestricted project."
        )
    primary = next(
        (m.provider for m in candidates if identity(m.provider) == identity(config.provider)),
        candidates[0].provider,
    )
    cheap = min(
        candidates,
        key=lambda m: (m.provider.input_per_million + m.provider.output_per_million, m.id),
    ).provider
    eligible = {identity(m.provider) for m in candidates}
    explicit = list(config.role_providers.values()) + [
        p for panel in config.role_panels.values() for p in panel
    ]
    if config.heldout_provider:
        explicit.append(config.heldout_provider)
    if any(identity(p) not in eligible for p in explicit):
        raise ValueError(
            "An explicit role override uses an unavailable or excluded model. Update Advanced model routing before creating this run."
        )
    result.provider = primary.model_copy(deep=True)
    result.cheap_provider = cheap.model_copy(deep=True)
    result.frontier_provider = next(
        (
            m.provider.model_copy(deep=True)
            for m in candidates
            if config.frontier_provider
            and identity(m.provider) == identity(config.frontier_provider)
        ),
        primary.model_copy(deep=True),
    )
    for role in FLASH_ROLES:
        if (
            role not in result.role_providers
            and role not in result.role_panels
            and role not in result.role_commands
        ):
            result.role_providers[role] = cheap.model_copy(deep=True)
    # Freeze eligible membership as well as routes. No status query occurs on resume.
    result.model_inventory = ModelInventory(models=candidates)
    return result


def guard_writer_models(config: ResearchConfig) -> None:
    """Native writer calls must never escape an explicit project allowlist."""
    if config.model_inventory is None or config.allowed_models is None:
        return
    from .paper_orchestra import resolve_writer_config

    options = resolve_writer_config(config)
    permitted = {
        identity(m.provider)
        for m in config.model_inventory.models
        if m.enabled and m.id in config.allowed_models
    }
    native = {
        m.provider.model
        for m in config.model_inventory.models
        if m.enabled
        and m.id in config.allowed_models
        and m.provider.base_url.rstrip("/")
        == "https://generativelanguage.googleapis.com/v1beta/openai"
        and m.provider.api_key_env == "GEMINI_API_KEY"
    }
    for key, name in options.items():
        if not key.endswith("_model_name") or not name:
            continue
        provider = options["compatible_models"].get(name)
        if (provider and identity(ProviderConfig.model_validate(provider)) not in permitted) or (
            not provider and name not in native
        ):
            raise ValueError(
                "The manuscript workflow requires a model outside this project's permissions: "
                + name
            )
