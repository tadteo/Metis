"""Inheritance is explicit, revisioned and independent of stored research runs."""

from pathlib import Path

import pytest

from autoresearch import model_settings as models
from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.engine import Engine
from autoresearch.settings import load_settings, save_settings
from autoresearch.store import ConflictError, Store


def save(store, scope, values, project=""):
    before = models.snapshot(store, scope, project)
    return models.save_scope(store, scope, project, values, before["revision"])


def test_global_workspace_project_inheritance_reset_and_existing_runs(tmp_path: Path):
    one, two = Store(tmp_path / "one"), Store(tmp_path / "two")
    old = Engine(one).create("Fixture", "Preserve recorded config", demo=True)
    recorded = one.get_config(old.id)
    save(one, "global", {"provider": {"model": "global-a"}, "laya": {"enabled": True}})
    assert load_settings(two)[0].provider.model == "global-a"
    assert load_settings(two)[0].laya.enabled
    save(one, "workspace", {"provider": {"model": "workspace-a"}})
    project = str(tmp_path / "source")
    save(one, "project", {"provider": {"model": "project-a"}}, project)
    assert models.snapshot(one, "project", project)["config"]["provider"]["model"] == "project-a"
    assert (
        models.snapshot(one, "project", str(tmp_path / "other"))["config"]["provider"]["model"]
        == "workspace-a"
    )
    save(two, "global", {"provider": {"model": "global-b"}, "laya": {"enabled": False}})
    assert models.snapshot(one, "project", project)["config"]["laya"]["enabled"] is False
    save(one, "project", {}, project)
    assert models.snapshot(one, "project", project)["config"]["provider"]["model"] == "workspace-a"
    save(one, "workspace", {})
    assert load_settings(one)[0].provider.model == "global-b"
    assert one.get_config(old.id) == recorded
    assert one.usage(old.id)["calls"] == 0


def test_legacy_choices_preserved_and_stale_parent_changes_conflict(tmp_path: Path):
    store = Store(tmp_path / "one")
    config = ResearchConfig()
    config.provider.model = "legacy"
    with store.connect() as db:
        db.execute("INSERT INTO settings VALUES(1,?,1)", (config.model_dump_json(),))
    before = models.snapshot(store, "workspace")
    assert before["legacy"] and before["config"]["provider"]["model"] == "legacy"
    save(store, "global", {"provider": {"model": "new-parent"}})
    with pytest.raises(ConflictError):
        models.save_scope(store, "workspace", "", {}, before["revision"])
    save(store, "workspace", {})
    assert load_settings(store)[0].provider.model == "new-parent"


def test_parent_snapshot_is_validated_and_cannot_change_project_or_credentials(tmp_path: Path):
    store = Store(tmp_path / "remote")
    config = ResearchConfig()
    config.project.source_dir = str(tmp_path / "project")
    save_settings(store, config, 0)
    save(store, "workspace", {})
    parent = models.select_models(config)
    parent["provider"]["model"] = "remote-global"
    models.receive_parent(store, parent)
    before = models.snapshot(store, "global")
    assert before["managed"]
    assert load_settings(store)[0].project.source_dir == config.project.source_dir
    assert load_settings(store)[0].provider.model == "remote-global"
    models.receive_parent(store, parent)
    assert models.snapshot(store, "global")["revision"] == before["revision"]
    with pytest.raises(ValueError, match="local console"):
        models.save_scope(store, "global", "", {}, before["revision"])
    with pytest.raises(ValueError):
        models.receive_parent(store, {**parent, "project": {"source_dir": "/unwanted"}})
    with pytest.raises(ValueError):
        models.receive_parent(store, {**parent, "provider": {"api_key_env": "a pasted secret"}})
    assert models.snapshot(store, "global")["revision"] == before["revision"]


def test_scoped_cli_and_project_resolution(tmp_path: Path):
    root, project = tmp_path / "workspace", tmp_path / "project"
    args = ["--state-dir", str(root), "settings"]
    assert main(args + ["--scope", "global", "set", "provider.model", '"global-cli"']) == 0
    assert (
        main(
            args
            + [
                "--scope",
                "project",
                "--project",
                str(project),
                "set",
                "provider.model",
                '"project-cli"',
            ]
        )
        == 0
    )
    store = Store(root)
    config = ResearchConfig()
    config.project.source_dir = str(project)
    assert models.resolve_models(store, config).provider.model == "project-cli"
    assert main(args + ["--scope", "project", "--project", str(project), "inherit"]) == 0
    assert models.resolve_models(store, config).provider.model == "global-cli"
    assert main(args + ["--scope", "global", "set", "execution.allow_local", "true"]) == 1


def test_unrelated_legacy_save_preserves_inheritance_and_project_boundaries(tmp_path):
    store = Store(tmp_path / "workspace")
    save(store, "global", {"provider": {"model": "global-a"}})
    config, revision = load_settings(store)
    config.budget.usd = 30
    save_settings(store, config, revision)
    save(store, "global", {"provider": {"model": "global-b"}})
    assert load_settings(store)[0].provider.model == "global-b"
    project = str(tmp_path / "project")
    config, revision = load_settings(store)
    config.project.source_dir = project
    save_settings(store, config, revision)
    save(store, "project", {"provider": {"model": "project-only"}}, project)
    config, revision = load_settings(store)
    config.budget.usd = 35
    save_settings(store, config, revision)
    assert (
        models.snapshot(store, "project", str(tmp_path / "other"))["config"]["provider"]["model"]
        == "global-b"
    )


def test_open_tui_resolves_new_defaults_unless_launch_config_is_explicit(tmp_path):
    from autoresearch.tui import ResearchApp

    store = Store(tmp_path / "workspace")
    inherited = ResearchApp(store)
    explicit_config = ResearchConfig()
    explicit_config.provider.model = "explicit-launch"
    explicit = ResearchApp(store, config=explicit_config)
    save(store, "global", {"provider": {"model": "updated-after-open"}})
    assert inherited._configuration("").provider.model == "updated-after-open"
    assert explicit._configuration("").provider.model == "explicit-launch"


def test_parent_changes_invalidate_legacy_editor_revision(tmp_path):
    store = Store(tmp_path / "workspace")
    save(store, "global", {"provider": {"model": "global-a"}})
    config, revision = load_settings(store)
    save(store, "global", {"provider": {"model": "global-b"}})
    config.budget.usd = 30
    with pytest.raises(ConflictError):
        save_settings(store, config, revision)
    assert load_settings(store)[0].provider.model == "global-b"


def test_cli_tui_passes_only_explicit_launch_config(tmp_path, monkeypatch):
    supplied = []

    class FakeApp:
        def __init__(self, store, config, *args, **kwargs):
            supplied.append(config)

        def run(self):
            pass

    monkeypatch.setattr("autoresearch.tui.ResearchApp", FakeApp)
    assert main(["--state-dir", str(tmp_path), "tui"]) == 0
    assert supplied == [None]
