"""Provider presets: sourced catalog, inventory mapping, key isolation, surfaces."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Input, Select, Static

from autoresearch import credentials, setup_cli
from autoresearch import provider_presets as presets
from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.model_inventory import AvailableModel, ModelInventory, prepare_models
from autoresearch.settings import load_settings, save_settings
from autoresearch.setup import inventory_checks, preflight
from autoresearch.store import Store
from autoresearch.tui import ResearchApp

SECRET = "fake-preset-key-0001"  # noqa: S105 - synthetic fixture


def raw_catalog() -> dict[str, Any]:
    text = resources.files("autoresearch").joinpath("assets/provider_presets.json").read_text()
    return json.loads(text)


def test_every_published_number_and_flag_carries_source_and_date() -> None:
    catalog = presets.load_catalog()
    assert catalog.catalog_version <= date(2026, 10, 8)
    unsourced: list[str] = []

    def walk(value: Any, path: str, sourced: bool) -> None:
        if isinstance(value, dict):
            here = "source_url" in value and "checked_at" in value
            for key, item in value.items():
                walk(item, f"{path}.{key}", here)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", False)
        elif (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and not sourced
            and path != "$.schema_version"
        ):
            unsourced.append(path)

    walk(raw_catalog(), "$", False)
    assert unsourced == []
    # Booleans that drive requests are sourced objects, not bare flags.
    for provider in catalog.providers:
        for model in provider.models:
            for item in (model.json_mode, model.streaming):
                assert item is None or item.source_url.startswith("https://")


def test_catalog_covers_requested_providers_and_literal_caveats() -> None:
    catalog = presets.load_catalog()
    ids = {p.id for p in catalog.providers}
    assert {"google", "mistral", "groq", "cerebras", "openrouter", "xai", "local"} <= ids
    flash = presets.find("google:gemini-3.8-flash", catalog)[1]
    daily = flash.free_tier.requests_per_day  # type: ignore[union-attr]
    assert daily is not None and daily.value == 20 and daily.basis == "observed"
    router = presets.find("openrouter:google/gemma-4-31b-it:free", catalog)
    assert router[1].free_tier.requests_per_day.value == 50  # type: ignore[union-attr]
    assert "1,000" in (router[1].free_tier.requests_per_day.note or "")  # type: ignore[union-attr]
    assert "train" in (presets.find("mistral:mistral-small-latest")[0].data_use.text)  # type: ignore[union-attr]
    for provider in catalog.providers:
        for model in provider.models:
            if model.capability:
                assert model.capability.basis == "provider-published"


def test_catalog_rejects_unsourced_future_or_insecure_values() -> None:
    base = raw_catalog()
    model = base["providers"][0]["models"][0]
    with pytest.raises(ValueError):
        presets.PresetCatalog.model_validate(
            {
                **base,
                "providers": [{**base["providers"][0], "models": [{**model, "context_window": 5}]}],
            }
        )
    insecure = {**model["context_window"], "source_url": "http://example.org"}
    with pytest.raises(ValueError):
        presets.PresetCatalog.model_validate(
            {
                **base,
                "providers": [
                    {**base["providers"][0], "models": [{**model, "context_window": insecure}]}
                ],
            }
        )
    future = {**model["context_window"], "checked_at": "2099-01-01"}
    with pytest.raises(ValueError, match="later than"):
        presets.PresetCatalog.model_validate(
            {
                **base,
                "providers": [
                    {**base["providers"][0], "models": [{**model, "context_window": future}]}
                ],
            }
        )
    with pytest.raises(ValueError, match="note"):
        presets.Sourced[int].model_validate(
            {
                "value": 1,
                "basis": "observed",
                "source_url": "https://a.example",
                "checked_at": "2026-01-01",
            }
        )


def test_preset_maps_to_inventory_entry_with_metadata_and_safe_defaults() -> None:
    provider, model = presets.find("google:gemini-3.8-flash")
    entry = presets.to_entry(provider, model)
    assert entry.id == "google-gemini-3-8-flash"
    assert entry.provider.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert entry.provider.api_key_env == "GEMINI_API_KEY"
    assert (entry.provider.input_per_million, entry.provider.output_per_million) == (0.75, 3.75)
    assert entry.provider.max_output_tokens == 12000  # never above the Metis default
    assert entry.preset is not None and entry.preset.model.context_window.value == 1048576  # type: ignore[union-attr]
    assert presets.limits(entry.preset.model)["requests_per_day"] == 20
    # Names match the quota-aware routing guard: limits.context_window_tokens / tokens_per_minute.
    assert entry.limits is not None
    assert entry.limits.context_window_tokens == 1048576 and entry.limits.requests_per_day == 20
    groq = presets.to_entry(*presets.find("groq:openai/gpt-oss-120b")).model_dump(mode="json")
    assert groq["limits"]["tokens_per_minute"] == 8000
    assert groq["limits"]["context_window_tokens"] == 131072
    # Unpublished prices keep a conservative estimate; loopback servers bill nothing.
    llama = presets.to_entry(*presets.find("groq:llama-3.3-70b-versatile"))
    assert llama.provider.input_per_million == presets.FALLBACK_INPUT
    local = presets.to_entry(*presets.find("local:qwen3:8b"), base_url="http://127.0.0.1:8000/v1")
    assert local.provider.model == "qwen3:8b" and local.provider.input_per_million == 0
    assert local.provider.json_mode is False and local.provider.streaming is False
    with pytest.raises(ValueError, match="Unknown provider"):
        presets.find("nowhere:model")
    with pytest.raises(ValueError, match="Choose a Groq model"):
        presets.find("groq:missing")


def test_adding_presets_refreshes_metadata_without_overwriting_user_edits() -> None:
    entry = presets.to_entry(*presets.find("groq:openai/gpt-oss-120b"))
    edited = entry.model_copy(deep=True)
    edited.provider.input_per_million = 9.0
    edited.preset = None
    edited.enabled = False
    inventory = presets.add_to_inventory(ModelInventory(models=[edited]), entry)
    assert len(inventory.models) == 1
    assert inventory.models[0].limits == entry.limits  # filled because the user had none
    assert inventory.models[0].provider.input_per_million == 9.0
    assert inventory.models[0].enabled is False and inventory.models[0].preset is not None
    second = presets.to_entry(*presets.find("groq:openai/gpt-oss-20b"))
    assert len(presets.add_to_inventory(inventory, second).models) == 2


def test_saved_inventories_and_pinned_configs_serialize_exactly_as_before() -> None:
    legacy = {
        "models": [
            {
                "id": "legacy",
                "label": "Legacy",
                "enabled": True,
                "provider": ResearchConfig().provider.model_dump(mode="json"),
            }
        ]
    }
    restored = ModelInventory.model_validate(legacy)
    assert restored.model_dump(mode="json") == legacy
    config = ResearchConfig(model_inventory=restored)
    dumped = config.model_dump(mode="json")
    assert "preset" not in json.dumps(dumped["model_inventory"])
    assert ResearchConfig.model_validate(dumped).model_dump(mode="json") == dumped
    # Preset metadata round-trips for new entries and is frozen into new runs.
    entry = presets.to_entry(*presets.find("cerebras:gpt-oss-120b"))
    again = AvailableModel.model_validate(entry.model_dump(mode="json"))
    assert again == entry


def test_routing_reads_metadata_from_frozen_run_inventory(monkeypatch) -> None:
    monkeypatch.setattr(credentials, "_session", {"GROQ_API_KEY": SECRET})
    entry = presets.to_entry(*presets.find("groq:openai/gpt-oss-120b"))
    config = ResearchConfig(provider=entry.provider, model_inventory=ModelInventory(models=[entry]))
    frozen = prepare_models(config)
    assert frozen.model_inventory is not None
    assert frozen.model_inventory.models[0].preset is not None
    assert (
        presets.limits(frozen.model_inventory.models[0].preset.model)["requests_per_minute"] == 30
    )


def test_readiness_reports_key_presence_limits_and_caveats_without_requests(monkeypatch) -> None:
    gemini = presets.to_entry(*presets.find("google:gemini-3.8-flash"))
    mistral = presets.to_entry(*presets.find("mistral:mistral-small-latest"))
    local = presets.to_entry(*presets.find("local:llama"))
    monkeypatch.setattr(credentials, "_session", {"GEMINI_API_KEY": SECRET})
    checks = {
        c["name"]: c for c in inventory_checks(ModelInventory(models=[gemini, mistral, local]))
    }
    assert checks["model:google-gemini-3-8-flash"]["status"] == "ok"
    assert "20 requests/day" in checks["model:google-gemini-3-8-flash"]["message"]
    assert "human reviewers" in checks["model:google-gemini-3-8-flash"]["message"]
    assert checks["model:mistral-mistral-small-latest"]["status"] == "warning"
    assert "MISTRAL_API_KEY missing" in checks["model:mistral-mistral-small-latest"]["message"]
    assert checks["model:local-llama"]["status"] == "ok"
    assert SECRET not in json.dumps(checks)
    config = ResearchConfig(
        provider=gemini.provider, model_inventory=ModelInventory(models=[gemini, mistral])
    )
    report = preflight(config)
    assert any(c["name"] == "model:mistral-mistral-small-latest" for c in report["checks"])
    assert SECRET not in json.dumps(report)


def test_cli_lists_shows_and_adds_presets_without_persisting_keys(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    prefix = ["--state-dir", str(tmp_path)]
    assert main(prefix + ["settings", "preset", "list"]) == 0
    listing = capsys.readouterr().out
    assert "google:gemini-3.8-flash" in listing and "Data use:" in listing
    assert main(prefix + ["settings", "preset", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["catalog_version"] == "2026-10-08"
    assert main(prefix + ["settings", "preset", "show", "groq:openai/gpt-oss-120b"]) == 0
    assert "30 requests/minute" in capsys.readouterr().out

    saved: list[tuple[str, str, str]] = []
    monkeypatch.setattr(setup_cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda prompt: SECRET)
    monkeypatch.setattr(credentials, "vault_available", lambda: True)
    monkeypatch.setattr(
        credentials, "save", lambda *args: saved.append(args) or {"source": "vault"}
    )
    assert main(prefix + ["settings", "preset", "add", "mistral:mistral-small-latest"]) == 0
    assert (
        main(prefix + ["settings", "preset", "add", "mistral:mistral-medium-latest", "--no-key"])
        == 0
    )
    out = capsys.readouterr().out
    assert "Free mode" in out and SECRET not in out
    assert saved == [("MISTRAL_API_KEY", SECRET, "vault")]
    config = load_settings(Store(tmp_path))[0]
    references = {
        f"{m.preset.provider}:{m.preset.model.id}"
        for m in config.model_inventory.models
        if m.preset  # type: ignore[union-attr]
    }
    assert {"mistral:mistral-small-latest", "mistral:mistral-medium-latest"} <= references
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()
    assert main(prefix + ["settings", "preset", "add"]) == 1
    assert main(prefix + ["settings", "preset", "add", "groq:x", "--no-key"]) == 1
    assert (
        main(
            prefix
            + [
                "settings",
                "preset",
                "add",
                "groq:openai/gpt-oss-20b",
                "--base-url",
                "http://127.0.0.1:1/v1",
            ]
        )
        == 1
    )


def test_cli_scoped_preset_add_targets_model_settings(tmp_path: Path) -> None:
    from autoresearch import model_settings

    prefix = ["--state-dir", str(tmp_path)]
    assert (
        main(
            prefix
            + [
                "settings",
                "preset",
                "add",
                "local:qwen3:8b",
                "--scope",
                "workspace",
                "--base-url",
                "http://127.0.0.1:8000/v1",
            ]
        )
        == 0
    )
    inventory = model_settings.snapshot(Store(tmp_path), "workspace")["config"]["model_inventory"]
    local = next(m for m in inventory["models"] if m["id"] == "local-qwen3-8b")
    assert local["provider"]["base_url"] == "http://127.0.0.1:8000/v1"


def test_shared_preset_change_rejects_untrusted_shapes() -> None:
    config = ResearchConfig()
    with pytest.raises(ValueError):
        presets.preset_changes(config, "google:gemini-3.8-flash")
    with pytest.raises(ValueError):
        presets.preset_changes(config, [])
    change = presets.preset_changes(config, ["google:gemini-3.8-flash", "groq:openai/gpt-oss-20b"])
    ids = [m["id"] for m in change["model_inventory"]["models"]]
    assert "groq-openai-gpt-oss-20b" in ids
    view = presets.preset_view(ModelInventory.model_validate(change["model_inventory"]))
    # The built-in Flash entry keeps its identity and gains published metadata.
    flash = next(v for v in view.values() if v["reference"] == "google:gemini-3.8-flash")
    assert "20 requests/day" in flash["limits"]


@pytest.mark.parametrize("size", [(120, 40), (80, 24)])
def test_tui_adds_preset_and_keeps_key_out_of_settings(tmp_path: Path, monkeypatch, size) -> None:
    saved: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        credentials, "save", lambda *args: saved.append(args) or {"source": "session"}
    )

    async def scenario() -> None:
        store = Store(tmp_path)
        app = ResearchApp(store)
        async with app.run_test(size=size) as pilot:
            app.action_settings()
            app._show_settings_section("model")
            await pilot.pause()
            choice = app.query_one("#preset-choice", Select)
            choice.value = "groq:openai/gpt-oss-120b"
            await pilot.pause()
            assert "30 requests/minute" in str(app.query_one("#preset-detail", Static).render())
            app.query_one("#preset-key", Input).value = SECRET
            app.query_one("#preset-storage", Select).value = "session"
            button = app.query_one("#preset-add")
            button.scroll_visible(animate=False)
            await pilot.pause()
            assert await pilot.click("#preset-add")
            await pilot.pause()
            assert app.query_one("#preset-key", Input).value == ""
        app.controller.join()

    asyncio.run(scenario())
    assert saved == [("GROQ_API_KEY", SECRET, "session")]
    config = load_settings(Store(tmp_path))[0]
    assert any(m.id == "groq-openai-gpt-oss-120b" for m in config.model_inventory.models)  # type: ignore[union-attr]
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()


def test_existing_settings_save_keeps_preset_metadata(tmp_path: Path) -> None:
    store = Store(tmp_path)
    config, revision = load_settings(store)
    config.model_inventory = presets.add_to_inventory(
        config.model_inventory or ModelInventory(), presets.to_entry(*presets.find("xai:grok-4.7"))
    )
    save_settings(store, config, revision)
    reloaded = load_settings(store)[0]
    entry = next(m for m in reloaded.model_inventory.models if m.provider.model == "grok-4.7")  # type: ignore[union-attr]
    assert entry.preset is not None and entry.preset.model.context_window.value == 500000  # type: ignore[union-attr]
