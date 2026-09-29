"""Behavior changes cannot silently alter a resumed scientific run."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from autoresearch import behavior
from autoresearch.catalog import ROOT
from autoresearch.config import ResearchConfig
from autoresearch.contracts import Idea, RunState
from autoresearch.engine import Engine
from autoresearch.memory import research_view
from autoresearch.paper_orchestra import materialize_raw_materials
from autoresearch.store import Store


def test_run_archives_resolved_behavior_and_budget_edits_do_not_change_it(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Public fixture", "Inspect behavior", demo=True)
    assert state.behavior is not None
    info = behavior.inspect_run(store, state)
    assert "Do not fabricate" in info["prompts"]["limitations"]
    assert set(info["workflow"]["nodes"]) >= {"subset", "full", "meta_refine", "integrity"}
    assert info["agents"]["coding_step"]["tools"]
    store.update_budget(state.id, usd=100)
    behavior.verify(store, state, store.get_config(state.id))
    assert store.usage(state.id)["calls"] == 0


def test_prompt_edit_blocks_resume_but_original_instructions_remain_inspectable(
    tmp_path: Path,
) -> None:
    custom = tmp_path / "specs"
    shutil.copytree(ROOT, custom)
    config = ResearchConfig(specification_dir=str(custom))
    store = Store(tmp_path / "state")
    engine = Engine(store, config)
    state = engine.create("Public fixture", "Prompt changes", demo=True)
    original = behavior.inspect_run(store, state)["prompts"]["limitations"]
    catalog = behavior.load_catalog(custom)
    prompt = custom / catalog.definition("limitations").prompts[0]
    prompt.write_text(prompt.read_text() + "\nChanged instruction for a new study.\n")
    result = engine.step(state.id)
    assert result.status == "blocked"
    assert "behavior changed" in result.error
    assert store.usage(state.id)["calls"] == 0
    assert behavior.inspect_run(store, result)["prompts"]["limitations"] == original


def test_runtime_drift_and_artifact_tampering_are_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Public fixture", "Executable changes", demo=True)
    monkeypatch.setattr(behavior, "runtime_manifest", lambda: {"changed.py": "0" * 64})
    with pytest.raises(ValueError, match="behavior changed"):
        behavior.verify(store, state, store.get_config(state.id))
    record = next(a for a in store.artifacts(state.id) if a["kind"] == "ai_behavior")
    (store.run_dir(state.id) / record["path"]).write_text("{}")
    with pytest.raises(ValueError, match="integrity check"):
        behavior.recorded(store, state)


def test_legacy_adoption_is_explicit_and_keeps_unknown_provenance_visible(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = RunState(id="abcdef123456", title="Legacy fixture", objective="Preserve history")
    store.create(state, ResearchConfig(mode="demo"))
    with pytest.raises(ValueError, match="legacy run"):
        behavior.verify(store, state, store.get_config(state.id))
    adopted = behavior.adopt_legacy(store, state.id)
    assert adopted.behavior is not None and adopted.behavior.legacy_adoption
    assert adopted.memory[-1]["original_provenance"] == "unavailable"
    behavior.verify(store, adopted, store.get_config(state.id))
    with pytest.raises(ValueError, match="already has pinned"):
        behavior.adopt_legacy(store, state.id)


def test_unknown_configured_agent_fails_before_creating_run(tmp_path: Path) -> None:
    config = ResearchConfig(prompt_overrides={"misspelled_role": "An unused instruction"})
    store = Store(tmp_path)
    with pytest.raises(ValueError, match="unknown configured agent"):
        Engine(store, config).create("Invalid", "Do not silently ignore role policy")
    assert store.list_runs() == []


def test_heldout_feedback_is_excluded_from_model_and_official_writer_views(tmp_path: Path) -> None:
    state = RunState(
        id="abcdef123456",
        title="Frozen fixture",
        objective="Independent evaluation",
        selected_idea="candidate",
        ideas=[Idea(id="candidate", title="Candidate", hypothesis="Test mechanism")],
        reviews=[
            {"kind": "peer_review", "feedback": "retain criticism"},
            {
                "kind": "heldout",
                "review": {"feedback": "HELDOUT_SENTINEL"},
                "optimization_feedback": False,
            },
        ],
        memory=[{"kind": "experiment", "status": "failed", "reason": "retain failure"}],
    )
    view = research_view(state)
    assert "HELDOUT_SENTINEL" not in json.dumps(view)
    assert "retain failure" in json.dumps(view) and "retain criticism" in json.dumps(view)
    materialize_raw_materials(state, tmp_path)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "HELDOUT_SENTINEL" not in path.read_text()
    assert "HELDOUT_SENTINEL" in state.model_dump_json()


def test_external_command_entrypoint_changes_are_detected(tmp_path: Path) -> None:
    import sys

    script = tmp_path / "adapter.py"
    script.write_text("# first adapter version\n")
    config = ResearchConfig(
        role_commands={"draft": [sys.executable, str(script)]},
        role_command_max_cost_usd={"draft": 1.0},
    )
    first = behavior.snapshot(config)
    assert first["agents"]["draft"]["resolved_provider"] == "external_command"
    assert first["agents"]["draft"]["resolved_model"] == "adapter_reported"
    assert "upstream_models" not in first["agents"]["draft"]
    script.write_text("# second adapter version\n")
    assert behavior.identity(first) != behavior.identity(behavior.snapshot(config))


def test_injected_provider_configuration_is_pinned() -> None:
    from autoresearch.contracts import ProviderConfig
    from autoresearch.providers import CompatibleProvider

    first = CompatibleProvider(ProviderConfig(model="first-model"))
    second = CompatibleProvider(ProviderConfig(model="second-model"))
    assert behavior.extension_manifest(
        {"provider": first}, strict=True
    ) != behavior.extension_manifest({"provider": second}, strict=True)


def test_live_custom_extensions_require_explicit_stable_identity() -> None:
    class OpaqueAdapter:
        pass

    class ConfiguredAdapter:
        def __init__(self, model: str) -> None:
            self.model = model
            self.calls = 0

        def behavior_identity(self) -> dict[str, str]:
            return {"model": self.model}

    with pytest.raises(ValueError, match="require behavior_identity"):
        behavior.extension_manifest({"provider": OpaqueAdapter()}, strict=True)
    adapter = ConfiguredAdapter("first-model")
    first = behavior.extension_manifest({"provider": adapter}, strict=True)
    adapter.calls += 1
    assert behavior.extension_manifest({"provider": adapter}, strict=True) == first
    adapter.model = "second-model"
    assert behavior.extension_manifest({"provider": adapter}, strict=True) != first


def test_relative_specification_path_is_persisted_absolutely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(ROOT, tmp_path / "specs")
    monkeypatch.chdir(tmp_path)
    store = Store(tmp_path / "state")
    engine = Engine(store, ResearchConfig(specification_dir="specs"))
    state = engine.create("Public fixture", "Resume from another cwd", demo=True)
    assert Path(store.get_config(state.id).specification_dir).is_absolute()
    monkeypatch.chdir(tmp_path.parent)
    assert engine.step(state.id).status != "blocked"


def test_nested_retrieval_provider_overrides_change_identity() -> None:
    from autoresearch.literature import Literature

    config = ResearchConfig()
    standard = Literature(config)
    empty = Literature(config, providers=[])
    assert behavior.extension_manifest(
        {"literature": standard}, strict=True
    ) != behavior.extension_manifest({"literature": empty}, strict=True)


def test_factory_classes_keep_their_own_implementation_identity() -> None:
    class FirstFactory:
        @staticmethod
        def behavior_identity() -> dict[str, str]:
            return {"configuration": "same"}

    class SecondFactory:
        @staticmethod
        def behavior_identity() -> dict[str, str]:
            return {"configuration": "same"}

    first = behavior.extension_manifest({"factory": FirstFactory}, strict=True)
    second = behavior.extension_manifest({"factory": SecondFactory}, strict=True)
    assert first != second
    assert "FirstFactory" in first["factory"]["implementation"]


def test_extensionless_adapter_bytes_are_pinned(tmp_path: Path) -> None:
    import sys

    script = tmp_path / "adapter"
    script.write_text("# first script\n")
    config = ResearchConfig(
        role_commands={"draft": [sys.executable, str(script)]},
        role_command_max_cost_usd={"draft": 1},
    )
    before = behavior.external_adapter_manifest(config)
    script.write_text("# changed script\n")
    assert behavior.external_adapter_manifest(config) != before


def test_relative_adapter_executable_is_normalized_before_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "adapter"
    script.write_text("#!/usr/bin/env python3\n")
    script.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    config = ResearchConfig(
        role_commands={"draft": ["./adapter"]}, role_command_max_cost_usd={"draft": 1}
    )
    store = Store(tmp_path / "state")
    state = Engine(store, config).create("Fixture", "Inspect adapter paths")
    assert store.get_config(state.id).role_commands["draft"][0] == str(script)
    monkeypatch.chdir(tmp_path.parent)
    behavior.verify(store, state, store.get_config(state.id))


@pytest.mark.parametrize("pending", ["coding", "zero_cost_reservation"])
def test_legacy_adoption_rejects_subordinate_pending_work(tmp_path: Path, pending: str) -> None:
    store = Store(tmp_path)
    state = RunState(
        id="abcdef123456", title="Legacy fixture", objective="Reconcile before adoption"
    )
    store.create(state, ResearchConfig(mode="demo"))
    if pending == "coding":
        folder = store.run_dir(state.id) / "coding" / "session"
        folder.mkdir(parents=True)
        (folder / "checkpoint.json").write_text(
            json.dumps(
                {"schema_version": 1, "pending": {"job_id": "remote-job"}, "completed": None}
            )
        )
    else:
        store.reserve(state.id, "limitations", 0, "uncertain-request")
    with pytest.raises(ValueError, match="reconcile legacy"):
        behavior.adopt_legacy(store, state.id)
    assert store.get_run(state.id).behavior is None
    assert not store.artifacts(state.id)
