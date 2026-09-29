"""Generic adapter billing, durable attempted-call identities and legacy recovery."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from autoresearch.accounting import SubordinateCall
from autoresearch.config import ResearchConfig
from autoresearch.contracts import RunState, Usage
from autoresearch.privacy import redact
from autoresearch.store import BudgetExceeded, ConflictError, Store


def create_store(tmp_path: Path, *, max_calls: int = 10, usd: float = 10) -> tuple[Store, RunState]:
    store = Store(tmp_path)
    config = ResearchConfig()
    config.budget.max_calls = max_calls
    config.budget.usd = usd
    state = RunState(id="a" * 12, title="Accounting fixture", objective="Retain every attempt")
    store.create(state, config)
    return store, state


def child(identifier: str, cost: float, *, namespace: str = "external_solver") -> SubordinateCall:
    return SubordinateCall(
        id=identifier,
        namespace=namespace,
        provider="fixture",
        model="scripted",
        usage=Usage(cost_usd=cost, input_tokens=10, output_tokens=2),
    )


def total(*children: SubordinateCall) -> Usage:
    return Usage(
        cost_usd=sum(c.usage.cost_usd for c in children),
        input_tokens=sum(c.usage.input_tokens for c in children),
        output_tokens=sum(c.usage.output_tokens for c in children),
        estimated=any(c.usage.estimated for c in children),
    )


def test_generic_children_count_once_and_parent_charges_once(tmp_path: Path) -> None:
    store, state = create_store(tmp_path, max_calls=3)
    parent = store.reserve(state.id, "independent_solver", 2, "batch", kind="aggregate")
    children = [child("one", 0.4), child("two", 0.3)]
    charge = total(*children)
    store.settle(parent, charge, subordinate_calls=[*children, children[0]])
    Store(tmp_path).settle(parent, charge, subordinate_calls=children)
    direct = store.reserve(state.id, "paper_orchestra", 1, "ordinary-direct-request")
    store.settle(direct, Usage(cost_usd=0.1))
    usage = store.usage(state.id)
    assert usage["cost_usd"] == pytest.approx(0.8)
    assert usage["input_tokens"] == 20
    assert usage["calls"] == 2
    assert usage["aggregate_jobs"] == usage["writer_jobs"] == 1
    assert usage["subordinate_calls"] == 2
    assert usage["model_calls_attempted"] == 3
    assert len([e for e in store.events(state.id) if e["kind"] == "subordinate_model_call"]) == 2
    with pytest.raises(BudgetExceeded):
        store.reserve(state.id, "any_future_agent", 0, "next")


def test_conflicting_replay_rolls_back_new_child_and_cannot_reassign_attempt(
    tmp_path: Path,
) -> None:
    store, state = create_store(tmp_path)
    parent = store.reserve(state.id, "first", 1, "batch", kind="aggregate")
    original = child("same", 0.2)
    store.settle(parent, total(original), subordinate_calls=[original])
    with pytest.raises(ConflictError, match="overwritten"):
        store.settle(
            parent,
            total(original),
            subordinate_calls=[child("uncommitted", 0), child("same", 0.1)],
        )
    assert [r["id"] for r in store.subordinate_calls(state.id)] == ["same"]
    other = store.reserve(state.id, "second", 1, "batch-two", kind="aggregate")
    with pytest.raises(ConflictError, match="another reservation"):
        store.settle(other, total(original), subordinate_calls=[original])
    assert store.usage(state.id)["reserved_usd"] == 1
    assert store.usage(state.id)["cost_usd"] == 0.2
    alternate_namespace = child("same", 0.2, namespace="another_adapter")
    store.settle(other, total(alternate_namespace), subordinate_calls=[alternate_namespace])
    assert store.usage(state.id)["model_calls_attempted"] == 2


def test_aggregate_cannot_erase_conservative_unknown_usage(tmp_path: Path) -> None:
    store, state = create_store(tmp_path)
    parent = store.reserve(state.id, "native_adapter", 1, "batch", kind="aggregate")
    uncertain = child("uncertain", 0.7)
    uncertain.status = "reserved"
    uncertain.usage.estimated = True
    with pytest.raises(ConflictError, match="understate"):
        store.settle(parent, Usage(), subordinate_calls=[uncertain])
    assert store.usage(state.id)["reserved_usd"] == 1
    assert not store.subordinate_calls(state.id)
    with pytest.raises(ConflictError, match="understate"):
        store.settle(
            parent,
            total(uncertain).model_copy(update={"estimated": False}),
            subordinate_calls=[uncertain],
        )
    store.settle(parent, total(uncertain), subordinate_calls=[uncertain])
    assert store.usage(state.id)["cost_usd"] == 0.7
    assert store.subordinate_calls(state.id)[0]["usage"]["estimated"]
    assert store.subordinate_calls(state.id)[0]["status"] == "reserved"
    with pytest.raises(ConflictError, match="overwritten"):
        store.settle(parent, Usage(), subordinate_calls=[])


@pytest.mark.parametrize("exceeded", ["money", "calls"])
def test_incurred_overruns_retain_parent_and_children_before_stopping(
    tmp_path: Path, exceeded: str
) -> None:
    store, state = create_store(tmp_path, max_calls=1 if exceeded == "calls" else 10)
    children = [child("one", 0.4), child("two", 0.3)]
    parent = store.reserve(
        state.id, "adapter", 0.1 if exceeded == "money" else 1, "batch", kind="aggregate"
    )
    with pytest.raises(BudgetExceeded, match="actual usage was recorded"):
        store.settle(parent, total(*children), subordinate_calls=children)
    assert store.usage(state.id)["cost_usd"] == 0.7
    assert store.usage(state.id)["model_calls_attempted"] == 2
    assert store.usage(state.id)["reserved_usd"] == 0
    store.settle(parent, total(*children), subordinate_calls=children)
    assert len(store.subordinate_calls(state.id)) == 2


def test_direct_reservation_cannot_hide_subordinate_attempts(tmp_path: Path) -> None:
    store, state = create_store(tmp_path)
    direct = store.reserve(state.id, "adapter", 1, "request")
    attempt = child("one", 0.1)
    with pytest.raises(ValueError, match="aggregate"):
        store.settle(direct, total(attempt), subordinate_calls=[attempt])
    assert store.usage(state.id)["reserved_usd"] == 1
    assert not store.subordinate_calls(state.id)


def legacy_store(
    root: Path,
    *,
    missing_final_event: bool = False,
    model: str = "",
    patterns: list[str] | None = None,
) -> tuple[str, list[dict]]:
    root.mkdir()
    state = RunState(id="b" * 12, title="Legacy fixture", objective="Preserve old attempts")
    config = ResearchConfig()
    config.budget.max_calls = 3
    config.privacy.redact_patterns = patterns or []
    records = [
        {"id": "old-one", "cost_usd": 0.5, "input_tokens": 5},
        {
            "id": "old-two",
            "cost_usd": 0.25,
            "input_tokens": 2,
            "estimated": True,
            "status": "reserved",
        },
    ]
    if model:
        for record in records:
            record["model"] = model
    with sqlite3.connect(root / "research.sqlite3") as db:
        db.executescript("""
            CREATE TABLE runs(id TEXT PRIMARY KEY,state TEXT NOT NULL,config TEXT NOT NULL,version INTEGER NOT NULL,paused INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE calls(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,reserved REAL NOT NULL,usage TEXT NOT NULL,request_hash TEXT NOT NULL);
            CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,timestamp TEXT NOT NULL,kind TEXT NOT NULL,stage TEXT NOT NULL,payload TEXT NOT NULL);
        """)
        db.execute(
            "INSERT INTO runs VALUES(?,?,?,?,?)",
            (state.id, state.model_dump_json(), config.model_dump_json(), 0, 0),
        )
        for identifier, role, status, reserved, usage in [
            ("direct", "critic", "settled", 1, Usage(cost_usd=0.2)),
            (
                "old-parent",
                "paper_orchestra",
                "settled",
                1,
                Usage(cost_usd=0.75, input_tokens=7, estimated=True),
            ),
            ("old-active", "paper_orchestra", "reserved", 1.5, Usage()),
        ]:
            db.execute(
                "INSERT INTO calls VALUES(?,?,?,?,?,?,?)",
                (identifier, state.id, role, status, reserved, usage.model_dump_json(), "request"),
            )
        for record in [records[0], records[0], *([] if missing_final_event else [records[1]])]:
            db.execute(
                "INSERT INTO events(run_id,timestamp,kind,stage,payload) VALUES(?,?,?,?,?)",
                (
                    state.id,
                    "2026-01-01",
                    "paper_orchestra_api_call",
                    "draft",
                    json.dumps(redact(record, config.privacy.redact_patterns)),
                ),
            )
    return state.id, records


@pytest.mark.parametrize("missing_final_event", [False, True])
def test_legacy_migration_preserves_cost_history_and_uncertain_parentage(
    tmp_path: Path, missing_final_event: bool
) -> None:
    root = tmp_path / "legacy"
    run_id, records = legacy_store(root, missing_final_event=missing_final_event)
    store = Store(root)
    usage = store.usage(run_id)
    assert usage["cost_usd"] == 0.95
    assert usage["reserved_usd"] == 1.5
    assert usage["calls"] == 3
    assert usage["aggregate_jobs"] == 2
    assert usage["model_calls_attempted"] == (2 if missing_final_event else 3)
    assert all(
        r["parent_status"] == "unassociated_legacy_event" for r in store.subordinate_calls(run_id)
    )
    assert len(store.events(run_id)) == (2 if missing_final_event else 3)
    reopened = Store(root)
    assert reopened.usage(run_id) == usage
    children = [SubordinateCall.from_record("paper_orchestra", record) for record in records]
    # A pre-ledger parent crash could have settled cost before writing all events.
    reopened.settle(
        "old-parent",
        Usage(cost_usd=0.75, input_tokens=7, estimated=True),
        subordinate_calls=children,
    )
    assert reopened.usage(run_id)["cost_usd"] == 0.95
    assert reopened.usage(run_id)["model_calls_attempted"] == 3
    assert all(r["parent_id"] == "old-parent" for r in reopened.subordinate_calls(run_id))
    assert any(r["usage"]["estimated"] for r in reopened.subordinate_calls(run_id))
    with pytest.raises(BudgetExceeded):
        reopened.reserve(run_id, "new-role", 0, "next")


@pytest.mark.parametrize(
    ("model", "patterns"),
    [
        ("private-fixture-model", ["private-.*"]),
        ("/" + "home" + "/" + "synthetic-person/model", []),
    ],
)
def test_legacy_redacted_child_reconciles_once_with_raw_journal(
    tmp_path: Path, model: str, patterns: list[str]
) -> None:
    root = tmp_path / "legacy"
    run_id, records = legacy_store(root, model=model, patterns=patterns)
    store = Store(root)
    original_events = store.events(run_id)
    children = [SubordinateCall.from_record("paper_orchestra", record) for record in records]
    charge = Usage(cost_usd=0.75, input_tokens=7, estimated=True)
    store.settle("old-parent", charge, subordinate_calls=children)
    assert store.usage(run_id)["cost_usd"] == 0.95
    assert store.usage(run_id)["model_calls_attempted"] == 3
    assert store.events(run_id) == original_events
    assert all(row["parent_id"] == "old-parent" for row in store.subordinate_calls(run_id))
    assert all(row["model"] == model for row in store.subordinate_calls(run_id))
    Store(root).settle("old-parent", charge, subordinate_calls=children)
    changed = SubordinateCall.from_record(
        "paper_orchestra", {**records[0], "model": "private-changed"}
    )
    with pytest.raises(ConflictError, match="overwritten"):
        store.settle("old-parent", charge, subordinate_calls=[changed])


def test_idempotent_intent_recovers_same_charge_across_store_reopen(tmp_path):
    store, state = create_store(tmp_path)
    call = store.reserve(
        state.id, "external_workflow", 1, "stable-intent", kind="aggregate", idempotent=True
    )
    reopened = Store(tmp_path)
    assert (
        reopened.reserve(
            state.id, "external_workflow", 1, "stable-intent", kind="aggregate", idempotent=True
        )
        == call
    )
    reopened.settle(call, Usage(cost_usd=0.25))
    assert (
        reopened.reserve(
            state.id, "external_workflow", 1, "stable-intent", kind="aggregate", idempotent=True
        )
        == call
    )
    assert (
        reopened.call_for_request(state.id, "external_workflow", "stable-intent")["status"]
        == "settled"
    )
    assert reopened.usage(state.id)["aggregate_jobs"] == 1
    assert reopened.usage(state.id)["cost_usd"] == 0.25


def test_idempotent_reservation_rejects_changed_cap_kind_or_ambiguous_history(tmp_path):
    store, state = create_store(tmp_path)
    store.reserve(state.id, "workflow", 1, "request", kind="aggregate", idempotent=True)
    for maximum, kind in [(2, "aggregate"), (1, "model")]:
        with pytest.raises(ConflictError, match="amount or kind"):
            store.reserve(state.id, "workflow", maximum, "request", kind=kind, idempotent=True)
    store.reserve(state.id, "workflow", 1, "request", kind="aggregate")
    with pytest.raises(ConflictError, match="ambiguous"):
        store.reserve(state.id, "workflow", 1, "request", kind="aggregate", idempotent=True)
    with pytest.raises(ConflictError, match="ambiguous"):
        store.call_for_request(state.id, "workflow", "request")
