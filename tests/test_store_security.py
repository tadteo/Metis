from __future__ import annotations

import os
from pathlib import Path

import pytest

from autoresearch.contracts import Usage
from autoresearch.engine import Engine
from autoresearch.store import BudgetExceeded, ConflictError, Store


@pytest.mark.parametrize("maximum", [-1.0, float("nan"), float("inf"), True])
def test_invalid_reservations_cannot_expand_the_budget(tmp_path: Path, maximum: float) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Budget", "Accounting validation", demo=True)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        store.reserve(state.id, "critic", maximum, "request")
    assert store.usage(state.id)["calls"] == 0


def test_settlement_is_idempotent_but_cannot_erase_actual_cost(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Budget", "Immutable accounting", demo=True)
    call = store.reserve(state.id, "critic", 1, "request")
    usage = Usage(cost_usd=0.5, input_tokens=100)
    store.settle(call, usage)
    store.settle(call, usage)
    with pytest.raises(ConflictError, match="cannot be overwritten"):
        store.settle(call, Usage(cost_usd=0))
    assert store.usage(state.id)["cost_usd"] == 0.5


def test_unexpected_overspend_is_recorded_before_stopping(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Budget", "Unexpected provider usage", demo=True)
    call = store.reserve(state.id, "critic", 0.1, "request")
    with pytest.raises(BudgetExceeded, match="exceeded its reservation"):
        store.settle(call, Usage(cost_usd=0.5))
    assert store.usage(state.id)["cost_usd"] == 0.5
    assert store.usage(state.id)["reserved_usd"] == 0


def test_failed_checkpoint_does_not_advance_in_memory_version(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = Engine(store).create("Checkpoint", "Atomic save", demo=True)
    previous_version, previous_date = state.version, state.updated_at
    with pytest.raises(TypeError):
        store.save(state, payload={"not_json": {1, 2}})
    assert state.version == previous_version
    assert state.updated_at == previous_date
    assert store.get_run(state.id).version == previous_version


def test_artifact_replacement_does_not_overwrite_hardlinks(tmp_path: Path) -> None:
    store = Store(tmp_path / "runtime")
    state = Engine(store).create("Artifact", "Private write", demo=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("original")
    folder = store.run_dir(state.id) / "artifacts"
    folder.mkdir(exist_ok=True)
    os.link(outside, folder / "paper.md")
    store.artifact(state.id, "manuscript", "paper.md", "new manuscript")
    assert outside.read_text() == "original"
    assert (folder / "paper.md").stat().st_mode & 0o777 == 0o600


def test_export_is_private_and_cannot_replace_existing_path(tmp_path: Path) -> None:
    store = Store(tmp_path / "runtime")
    state = Engine(store).create("Export", "Private write", demo=True)
    target = tmp_path / "export.json"
    store.export_run(state.id, target, include_private=True)
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        store.export_run(state.id, target)
