"""Versioned provider presets: published endpoints, prices and free-tier limits.

The catalog is data, not a measurement. Every number carries its source page and
check date; unknown values stay null. Capability notes repeat what a provider
publishes about its own model and are never Metis-measured quality. Applying a
preset writes only a key *variable name*; secrets stay with ``credentials``.
"""

from __future__ import annotations

import json
import re
from datetime import date
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .contracts import Model, ProviderConfig

if TYPE_CHECKING:
    from .model_inventory import AvailableModel, ModelInventory

T = TypeVar("T", int, float, bool)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# ProviderConfig defaults; used only when a provider publishes no price.
FALLBACK_INPUT = ProviderConfig().input_per_million
FALLBACK_OUTPUT = ProviderConfig().output_per_million


def _https(url: str) -> str:
    if urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
        raise ValueError("Source URLs must be absolute HTTPS addresses")
    return url


class Source(Model):
    source_url: str
    checked_at: date

    @field_validator("source_url")
    @classmethod
    def https_source(cls, value: str) -> str:
        return _https(value)


class Sourced(Source, Generic[T]):
    """A published value together with the page that states it."""

    value: T
    # "observed": seen in a provider response (e.g. a quota error), not on a docs page.
    basis: Literal["published", "observed"] = "published"
    note: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def observed_needs_note(self) -> Sourced[T]:
        if self.basis == "observed" and not self.note:
            raise ValueError("Observed values must describe the observation in a note")
        return self

    @field_validator("value")
    @classmethod
    def non_negative(cls, value: T) -> T:
        if not isinstance(value, bool) and value < 0:
            raise ValueError("Published limits and prices are non-negative")
        return value


class FreeTier(Model):
    """Published free-tier limits. ``None`` means not published or not found."""

    available: Sourced[bool] | None = None
    requests_per_second: Sourced[float] | None = None
    requests_per_minute: Sourced[int] | None = None
    requests_per_hour: Sourced[int] | None = None
    requests_per_day: Sourced[int] | None = None
    tokens_per_minute: Sourced[int] | None = None
    tokens_per_hour: Sourced[int] | None = None
    tokens_per_day: Sourced[int] | None = None
    tokens_per_month: Sourced[int] | None = None
    note: str | None = Field(default=None, max_length=600)


class Capability(Source):
    """Provider-published positioning. Never a Metis measurement."""

    basis: Literal["provider-published"] = "provider-published"
    tier: Literal["frontier", "strong", "standard", "light", "unknown"] = "unknown"
    note: str = Field(min_length=1, max_length=400)


class DataUse(Source):
    text: str = Field(min_length=1, max_length=600)


class PresetModel(Model):
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=120)
    status: str = Field(default="unknown", max_length=40)
    json_mode: Sourced[bool] | None = None
    streaming: Sourced[bool] | None = None
    context_window: Sourced[int] | None = None
    max_output_tokens: Sourced[int] | None = None
    input_per_million: Sourced[float] | None = None
    output_per_million: Sourced[float] | None = None
    free_tier: FreeTier | None = None
    capability: Capability | None = None
    data_use: DataUse | None = None
    notes: list[str] = Field(default_factory=list, max_length=8)


class PresetProvider(Model):
    id: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    label: str = Field(min_length=1, max_length=80)
    base_url: str
    api_key_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    key_required: bool = True
    key_url: str | None = None
    custom_models: bool = False
    data_use: DataUse | None = None
    notes: list[str] = Field(default_factory=list, max_length=8)
    models: list[PresetModel] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def endpoint(self) -> PresetProvider:
        parts = urlsplit(self.base_url)
        local = parts.hostname in LOCAL_HOSTS
        if parts.scheme != "https" and not (local and parts.scheme == "http"):
            raise ValueError(f"{self.id}: remote endpoints must use HTTPS")
        if local and self.key_required:
            raise ValueError(f"{self.id}: loopback servers need no key")
        if not self.models and not self.custom_models:
            raise ValueError(f"{self.id}: list models or allow custom model IDs")
        if len({m.id for m in self.models}) != len(self.models):
            raise ValueError(f"{self.id}: model IDs must be unique")
        if self.key_url is not None:
            _https(self.key_url)
        return self


class PresetCatalog(Model):
    schema_version: Literal[1]
    catalog_version: date
    providers: list[PresetProvider] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def consistent(self) -> PresetCatalog:
        if len({p.id for p in self.providers}) != len(self.providers):
            raise ValueError("Provider IDs must be unique")
        for checked in _dates(self.model_dump()):
            if checked > self.catalog_version:
                raise ValueError("A source check date is later than the catalog version")
        return self


class ModelLimits(Model):
    """Flat limits on an inventory entry, named for routing's size/rate guards.

    Copied from catalog values (None = unknown); rate limits are the *free-tier* figures.
    Stored for quota-aware routing and model selection, which are separate work: nothing
    on this branch enforces them. Field names match that work's reader
    (``limits.context_window_tokens``, ``limits.tokens_per_minute``). Users can change
    them through ``metis settings set`` or an imported inventory.
    """

    context_window_tokens: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    requests_per_second: float | None = Field(default=None, gt=0)
    requests_per_minute: int | None = Field(default=None, gt=0)
    requests_per_hour: int | None = Field(default=None, gt=0)
    requests_per_day: int | None = Field(default=None, gt=0)
    tokens_per_minute: int | None = Field(default=None, gt=0)
    tokens_per_hour: int | None = Field(default=None, gt=0)
    tokens_per_day: int | None = Field(default=None, gt=0)
    tokens_per_month: int | None = Field(default=None, gt=0)


def model_limits(model: PresetModel) -> ModelLimits:
    """Inventory limits from a preset model; free-tier figures apply to free keys."""
    data: dict[str, Any] = {key: value or None for key, value in limits(model).items()}
    data["context_window_tokens"] = model.context_window.value if model.context_window else None
    data["max_output_tokens"] = model.max_output_tokens.value if model.max_output_tokens else None
    return ModelLimits.model_validate(data)


class ModelPreset(Model):
    """Catalog metadata stored on an inventory entry for routing and display."""

    catalog_version: date
    provider: str
    provider_label: str
    key_required: bool = True
    key_url: str | None = None
    data_use: DataUse | None = None
    model: PresetModel


def _dates(value: Any) -> list[date]:
    if isinstance(value, dict):
        found = [value["checked_at"]] if isinstance(value.get("checked_at"), date) else []
        return found + [d for item in value.values() for d in _dates(item)]
    if isinstance(value, list):
        return [d for item in value for d in _dates(item)]
    return []


@cache
def load_catalog() -> PresetCatalog:
    text = resources.files("autoresearch").joinpath("assets/provider_presets.json").read_text()
    return PresetCatalog.model_validate(json.loads(text))


def find(
    reference: str, catalog: PresetCatalog | None = None
) -> tuple[PresetProvider, PresetModel]:
    """Resolve ``provider:model``. Custom-model providers accept any model ID."""
    catalog = catalog or load_catalog()
    provider_id, _, model_id = reference.partition(":")
    provider = next((p for p in catalog.providers if p.id == provider_id), None)
    if provider is None:
        choices = ", ".join(p.id for p in catalog.providers)
        raise ValueError(f"Unknown provider preset {provider_id!r}; choose one of: {choices}")
    model = next((m for m in provider.models if m.id == model_id), None)
    if model is None and provider.custom_models and model_id.strip():
        model = PresetModel(id=model_id.strip(), label=model_id.strip())
    if model is None:
        listed = ", ".join(m.id for m in provider.models) or "any model ID your server serves"
        raise ValueError(f"Choose a {provider.label} model: {listed}")
    return provider, model


def entry_id(provider: PresetProvider, model: PresetModel) -> str:
    return (provider.id + "-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", model.id).strip("-"))[:80]


def to_entry(
    provider: PresetProvider,
    model: PresetModel,
    *,
    catalog_version: date | None = None,
    base_url: str | None = None,
) -> AvailableModel:
    """Map a preset to an inventory entry. No key value is read or written."""
    from .model_inventory import AvailableModel

    if base_url is not None:
        if not provider.custom_models:
            raise ValueError("A custom address applies only to the local compatible server preset")
        base_url = loopback_endpoint(base_url)
    defaults = ProviderConfig()
    # A loopback server bills nothing; an unpublished remote price keeps a conservative estimate.
    fallback = (0.0, 0.0) if not provider.key_required else (FALLBACK_INPUT, FALLBACK_OUTPUT)
    input_price = model.input_per_million.value if model.input_per_million else fallback[0]
    output_price = model.output_per_million.value if model.output_per_million else fallback[1]
    max_output = defaults.max_output_tokens
    if model.max_output_tokens is not None:
        max_output = max(256, min(model.max_output_tokens.value, max_output))
    config = ProviderConfig(
        name=provider.id,
        base_url=base_url or provider.base_url,
        model=model.id,
        api_key_env=provider.api_key_env,
        input_per_million=input_price,
        output_per_million=output_price,
        long_input_per_million=input_price,
        long_output_per_million=output_price,
        max_output_tokens=max_output,
        # Unknown capabilities fall back to the most widely supported request shape.
        json_mode=model.json_mode.value if model.json_mode else False,
        streaming=model.streaming.value if model.streaming else False,
    )
    preset = ModelPreset(
        catalog_version=catalog_version or load_catalog().catalog_version,
        provider=provider.id,
        provider_label=provider.label,
        key_required=provider.key_required,
        key_url=provider.key_url,
        data_use=model.data_use or provider.data_use,
        model=model,
    )
    return AvailableModel(
        id=entry_id(provider, model),
        label=f"{model.label} · {provider.label}"[:120],
        provider=config,
        preset=preset,
        limits=model_limits(model),
    )


def loopback_endpoint(url: str) -> str:
    """A custom local-server address: loopback host, no credentials, query or fragment."""
    parts = urlsplit(url.strip())
    if (
        parts.scheme not in {"http", "https"}
        or parts.hostname not in LOCAL_HOSTS
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "The local server preset needs a loopback address such as http://127.0.0.1:11434/v1"
        )
    return url.strip()


def add_to_inventory(inventory: ModelInventory, entry: AvailableModel) -> ModelInventory:
    """Add or refresh one preset entry; never drop or relabel an unrelated row.

    An entry with the same endpoint/model/key identity gains fresh metadata and is enabled
    again; its own prices and limits stay. A different model that merely shares the
    generated ID keeps its row, and the new entry receives a distinct ID.
    """
    from .model_inventory import ModelInventory, identity

    models = list(inventory.models)
    for index, current in enumerate(models):
        if identity(current.provider) == identity(entry.provider):
            refreshed: dict[str, Any] = {"preset": entry.preset, "enabled": True}
            if current.limits is None:
                refreshed["limits"] = entry.limits
            models[index] = current.model_copy(update=refreshed, deep=True)
            return ModelInventory(models=models)
    taken = {m.id for m in models}
    candidate, suffix = entry.id, 2
    while candidate in taken:
        candidate = f"{entry.id[:76]}-{suffix}"
        suffix += 1
    models.append(entry.model_copy(update={"id": candidate}, deep=True))
    return ModelInventory(models=models)


def sanitize_inventory(previous: ModelInventory, incoming: ModelInventory) -> ModelInventory:
    """Keep catalog metadata server-side: an edit may retain, never invent, a preset."""
    from .model_inventory import ModelInventory, identity

    stored = {m.id: m for m in previous.models}
    models = []
    for entry in incoming.models:
        old = stored.get(entry.id)
        keep = old is not None and identity(old.provider) == identity(entry.provider)
        models.append(
            entry.model_copy(update={"preset": old.preset if keep and old else None}, deep=True)
        )
    return ModelInventory(models=models)


LIMIT_LABELS = (
    ("requests_per_second", "requests/second"),
    ("requests_per_minute", "requests/minute"),
    ("requests_per_hour", "requests/hour"),
    ("requests_per_day", "requests/day"),
    ("tokens_per_minute", "tokens/minute"),
    ("tokens_per_hour", "tokens/hour"),
    ("tokens_per_day", "tokens/day"),
    ("tokens_per_month", "tokens/month"),
)


def limits(model: PresetModel) -> dict[str, int | float | None]:
    """Flat published free-tier limits for routing and quota decisions (None = unknown)."""
    tier = model.free_tier or FreeTier()
    result: dict[str, int | float | None] = {}
    for key, _ in LIMIT_LABELS:
        item = getattr(tier, key)
        result[key] = item.value if item is not None else None
    return result


def limits_text(model: PresetModel) -> str:
    tier = model.free_tier
    if tier is None:
        return "No free tier published."
    if tier.available is not None and not tier.available.value:
        return "Not available on the free tier" + (f". {tier.note}" if tier.note else ".")
    parts = [
        f"{getattr(tier, key).value:,} {label}"
        + (
            " (observed on one account, not published)"
            if getattr(tier, key).basis == "observed"
            else ""
        )
        for key, label in LIMIT_LABELS
        if getattr(tier, key) is not None
    ]
    text = "Free tier: " + ("; ".join(parts) if parts else "limits not published")
    return text + (f". {tier.note}" if tier.note else ".")


def summary(provider: PresetProvider, model: PresetModel) -> dict[str, Any]:
    """Display projection shared by CLI, TUI and the browser."""
    data_use = model.data_use or provider.data_use

    def value(item: Sourced[Any] | None) -> Any:
        return item.value if item is not None else None

    return {
        "reference": f"{provider.id}:{model.id}",
        "provider": provider.id,
        "provider_label": provider.label,
        "model": model.id,
        "label": model.label,
        "status": model.status,
        "base_url": provider.base_url,
        "api_key_env": provider.api_key_env,
        "key_required": provider.key_required,
        "key_url": provider.key_url,
        "json_mode": value(model.json_mode),
        "streaming": value(model.streaming),
        "context_window": value(model.context_window),
        "max_output_tokens": value(model.max_output_tokens),
        "input_per_million": value(model.input_per_million),
        "output_per_million": value(model.output_per_million),
        "free_tier": limits(model),
        "limits": limits_text(model)
        if provider.key_required
        else "No provider quota; your own server's capacity applies.",
        "capability": model.capability.note if model.capability else None,
        "capability_basis": "Provider-published description; not measured by Metis."
        if model.capability
        else None,
        "data_use": data_use.text if data_use else None,
        "notes": list(model.notes),
        "provider_notes": list(provider.notes),
    }


def catalog_view(catalog: PresetCatalog | None = None) -> dict[str, Any]:
    catalog = catalog or load_catalog()
    return {
        "catalog_version": catalog.catalog_version.isoformat(),
        "providers": [
            {
                "id": p.id,
                "label": p.label,
                "base_url": p.base_url,
                "api_key_env": p.api_key_env,
                "key_required": p.key_required,
                "custom_models": p.custom_models,
                "key_url": p.key_url,
                "models": [summary(p, m) for m in p.models],
                "data_use": p.data_use.text if p.data_use else None,
                "notes": p.notes,
            }
            for p in catalog.providers
        ],
    }


def preset_changes(config: Any, references: Any, base_url: Any = "") -> dict[str, Any]:
    """Inventory change adding catalog presets (browser and TUI share this rule)."""
    from .model_inventory import initial_inventory

    if (
        not isinstance(references, list)
        or not 1 <= len(references) <= 40
        or not all(isinstance(item, str) and len(item) <= 240 for item in references)
    ):
        raise ValueError("Choose between 1 and 40 preset models")
    if not isinstance(base_url, str) or len(base_url) > 2048:
        raise ValueError("Endpoint must be text")
    catalog = load_catalog()
    inventory = config.model_inventory or initial_inventory(config)
    for reference in references:
        provider, model = find(reference, catalog)
        override = base_url if provider.custom_models and base_url.strip() else None
        entry = to_entry(
            provider, model, catalog_version=catalog.catalog_version, base_url=override
        )
        inventory = add_to_inventory(inventory, entry)
    return {"model_inventory": inventory.model_dump(mode="json")}


def preset_view(inventory: ModelInventory) -> dict[str, dict[str, Any]]:
    """Literal limit/caveat text for inventory rows that came from a preset."""
    return {
        entry.id: {
            "reference": f"{entry.preset.provider}:{entry.preset.model.id}",
            "catalog_version": entry.preset.catalog_version.isoformat(),
            "limits": limits_text(entry.preset.model)
            if entry.preset.key_required
            else "No provider quota; your own server's capacity applies.",
            "data_use": entry.preset.data_use.text if entry.preset.data_use else None,
            "capability": entry.preset.model.capability.note
            if entry.preset.model.capability
            else None,
        }
        for entry in inventory.models
        if entry.preset is not None
    }


def preset_options(catalog: PresetCatalog | None = None) -> list[tuple[str, str]]:
    """Terminal picker entries; ``provider:`` asks for a custom model ID."""
    catalog = catalog or load_catalog()
    options = []
    for provider in catalog.providers:
        options += [
            (f"{provider.label} · {m.label}", f"{provider.id}:{m.id}") for m in provider.models
        ]
        if provider.custom_models:
            options.append((f"{provider.label} · enter a model ID", f"{provider.id}:"))
    return options


def preset_detail(reference: object) -> str:
    """Plain-text description of one preset for terminal surfaces."""
    if not isinstance(reference, str) or ":" not in reference:
        return ""
    provider, model = find(reference if not reference.endswith(":") else reference + "model")
    data = summary(provider, model)
    if reference.endswith(":"):
        lines = [f"{provider.label} at {provider.base_url} (change it in Advanced settings)."]
    else:
        price = (
            "Price not published"
            if data["input_per_million"] is None or data["output_per_million"] is None
            else f"${data['input_per_million']:g} / ${data['output_per_million']:g} per million tokens"
        )
        context = data["context_window"]
        lines = [
            f"{data['label']}  ·  {provider.api_key_env}",
            f"{price}  ·  context {'not published' if context is None else f'{context:,} tokens'}",
        ]
    lines.append(str(data["limits"]))
    if data["data_use"]:
        lines.append(f"Data use: {data['data_use']}")
    if data["capability"]:
        lines.append(f"Provider description, not measured by Metis: {data['capability']}")
    lines += [str(note) for note in [*data["notes"], *data["provider_notes"]]]
    return "\n".join(lines)
