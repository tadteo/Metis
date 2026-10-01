"""Automatic routing is bounded by host access, project permissions and run snapshots."""

from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import ProviderConfig
from autoresearch.model_inventory import (
    AvailableModel,
    ModelInventory,
    guard_writer_models,
    initial_inventory,
    prepare_models,
)
from autoresearch.model_settings import save_scope, snapshot
from autoresearch.routing import resolve_route
from autoresearch.store import Store


def config():
    value = ResearchConfig()
    value.model_inventory = initial_inventory(value)
    return value


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(
        "autoresearch.credentials.resolve", lambda name: ("fixture-key-only", "environment")
    )


def test_connected_flash_is_automatic_and_critical_work_retains_primary(keys):
    original = config()
    prepared = prepare_models(original)
    assert resolve_route(prepared, "limitations").provider.name == "google"
    assert resolve_route(prepared, "intake").provider.name == "xai"
    assert original.role_providers == {}
    assert prepared.laya == original.laya
    assert prepared.pipeline == original.pipeline


def test_missing_flash_key_does_not_require_a_manual_profile(monkeypatch):
    monkeypatch.setattr(
        "autoresearch.credentials.resolve",
        lambda name: ("fixture-key-only" if name == "XAI_API_KEY" else "", "environment"),
    )
    prepared = prepare_models(config())
    assert resolve_route(prepared, "limitations").provider.name == "xai"
    assert len(prepared.model_inventory.models) == 1


def test_permissions_never_fall_back_to_excluded_models(keys, monkeypatch):
    value = config()
    google = next(m for m in value.model_inventory.models if m.provider.name == "google")
    value.allowed_models = [google.id]
    prepared = prepare_models(value)
    assert prepared.provider.name == "google"
    assert prepared.frontier_provider.name == "google"
    monkeypatch.setattr(
        "autoresearch.credentials.resolve",
        lambda name: ("fixture-key-only" if name == "XAI_API_KEY" else "", "environment"),
    )
    with pytest.raises(ValueError, match="No configured model"):
        prepare_models(value)
    # Already resolved routes never consult changing credentials.
    assert resolve_route(prepared, "intake").provider.name == "google"


def test_empty_unknown_and_legacy_allowlist_cannot_escape(keys):
    for ids in ([], ["unknown"]):
        value = config()
        value.allowed_models = ids
        with pytest.raises(ValueError, match="No configured model"):
            prepare_models(value)
    with pytest.raises(ValueError, match="require a configured"):
        prepare_models(ResearchConfig(allowed_models=["x"]))


def test_native_writer_alias_does_not_authorize_another_provider(keys):
    value = config()
    fake = AvailableModel(
        id="fake",
        label="Fake",
        provider=ProviderConfig(
            base_url="http://127.0.0.1:1234/v1", model=value.paper_orchestra.literature_model_name
        ),
    )
    value.model_inventory = ModelInventory(models=[fake])
    value.provider = fake.provider
    value.allowed_models = ["fake"]
    prepared = prepare_models(value)
    with pytest.raises(ValueError, match="manuscript workflow"):
        guard_writer_models(prepared)


def test_explicit_overrides_and_system_one_are_not_silently_replaced(keys):
    value = config()
    value.role_providers["intake"] = ProviderConfig(model="missing")
    with pytest.raises(ValueError, match="explicit role override"):
        prepare_models(value)
    with pytest.raises(ValueError, match="System 1"):
        ModelInventory(
            models=[AvailableModel(id="laya", label="Laya", provider=ProviderConfig(name="laya"))]
        )


def test_legacy_absent_inventory_inherits_and_nonmodel_fields_survive(tmp_path: Path):
    store = Store(tmp_path / "workspace")
    legacy = ResearchConfig()
    legacy.budget.usd = 123
    legacy.laya.enabled = True
    data = legacy.model_dump()
    data.pop("model_inventory")
    data.pop("allowed_models")
    import json

    with store.connect() as db:
        db.execute("INSERT INTO settings VALUES(1,?,1)", (json.dumps(data),))
    before = snapshot(store, "global")
    save_scope(
        store,
        "global",
        "",
        {"model_inventory": initial_inventory(legacy).model_dump()},
        before["revision"],
    )
    effective = snapshot(store)
    assert effective["config"]["model_inventory"] is not None
    assert effective["config"]["budget"]["usd"] == 123
    assert effective["config"]["laya"]["enabled"] is True


def test_all_project_models_inherit_future_global_additions(tmp_path: Path):
    store = Store(tmp_path / "workspace")
    project = str(tmp_path / "project")
    before = snapshot(store, "project", project)
    assert "model_inventory" not in before["overrides"]
    save_scope(
        store,
        "project",
        project,
        {**before["overrides"], "allowed_models": None},
        before["revision"],
    )
    global_view = snapshot(store, "global")
    inventory = ModelInventory.model_validate(global_view["config"]["model_inventory"])
    inventory.models.append(
        AvailableModel(id="extra", label="Extra", provider=ProviderConfig(model="extra"))
    )
    save_scope(
        store, "global", "", {"model_inventory": inventory.model_dump()}, global_view["revision"]
    )
    after = snapshot(store, "project", project)
    assert len(after["config"]["model_inventory"]["models"]) == 3


def test_fresh_global_sync_and_laya_edit_preserve_inventory(tmp_path: Path):
    from autoresearch.model_settings import global_snapshot

    store = Store(tmp_path / "workspace")
    assert global_snapshot()["model_inventory"] is not None
    before = snapshot(store)
    save_scope(store, "workspace", "", {"laya": before["config"]["laya"]}, before["revision"])
    assert snapshot(store)["config"]["model_inventory"] is not None


def test_created_run_freezes_automatic_routes(tmp_path: Path, keys, monkeypatch):
    from autoresearch.engine import Engine

    store = Store(tmp_path / "runs")
    value = config()
    run = Engine(store, value).create("Synthetic routing", "Verify model snapshot")
    saved = store.get_config(run.id)
    assert resolve_route(saved, "limitations").provider.name == "google"
    monkeypatch.setattr("autoresearch.credentials.resolve", lambda name: ("", "missing"))
    assert resolve_route(store.get_config(run.id), "limitations").provider.name == "google"
    assert value.role_providers == {}


def test_legacy_global_routing_and_sync_remain_explicit(tmp_path: Path, monkeypatch):
    import json

    from autoresearch.model_settings import global_snapshot, global_store

    monkeypatch.setenv("METIS_SETTINGS_HOME", str(tmp_path / "isolated-global"))
    custom = ProviderConfig(model="legacy-custom").model_dump(mode="json")
    with global_store().connect() as db:
        db.execute(
            "INSERT INTO model_settings VALUES(?,?,?)",
            ("global", json.dumps({"provider": custom}), 1),
        )
    config = ResearchConfig.model_validate(snapshot(Store(tmp_path / "workspace"))["config"])
    assert config.model_inventory is None
    assert global_snapshot()["model_inventory"] is None
    assert prepare_models(config).provider.model == "legacy-custom"


def test_advanced_primary_edit_uses_explicit_routing(tmp_path: Path):
    from autoresearch.settings import load_settings, save_settings

    store = Store(tmp_path / "workspace")
    config, revision = load_settings(store)
    config.provider.model = "explicit-custom"
    save_settings(store, config, revision)
    saved, _ = load_settings(store)
    assert saved.model_inventory is None
    assert prepare_models(saved).provider.model == "explicit-custom"


def test_conflicting_file_primary_is_rejected(keys):
    value = ResearchConfig.model_validate_json(config().model_dump_json())
    value.provider.model = "explicit-custom"
    with pytest.raises(ValueError, match="primary model is outside"):
        prepare_models(value)
