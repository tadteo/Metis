"""Writer retries reserve only unspent capacity and reconcile interrupted parents."""

import json

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import RunState
from autoresearch.store import ConflictError, Store
from autoresearch.writer_accounting import WriterAccounting


def setup(tmp_path):
    config = ResearchConfig()
    config.budget.usd = 20
    store = Store(tmp_path / "state")
    state = RunState(id="abcdef123456", title="Writer", objective="Recover usage")
    store.create(state, config)
    job = tmp_path / "job"
    job.mkdir()
    return store, state, job


def spend(job, identifier, amount):
    with (job / "usage.jsonl").open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "id": identifier,
                    "cost_usd": amount,
                    "input_tokens": 3,
                    "output_tokens": 4,
                    "estimated": False,
                }
            )
            + "\n"
        )


def test_writer_resume_reserves_only_cumulative_remaining_capacity(tmp_path):
    store, state, job = setup(tmp_path)
    accounting = WriterAccounting(job, store, state, "fingerprint")
    accounting.reserve_remaining(15)
    spend(job, "first", 8)
    accounting.reconcile()
    assert store.usage(state.id)["cost_usd"] == 8
    restored = WriterAccounting(job, store, state, "fingerprint")
    restored.reserve_remaining(15)
    assert store.usage(state.id)["reserved_usd"] == 7
    spend(job, "second", 2)
    restored.reconcile()
    assert store.usage(state.id)["cost_usd"] == 10
    assert store.usage(state.id)["reserved_usd"] == 0


def test_parent_crash_recovers_reservation_before_completed_fast_path(tmp_path):
    store, state, job = setup(tmp_path)
    WriterAccounting(job, store, state, "fingerprint").reserve_remaining(15)
    spend(job, "completed-in-child", 8)
    # A new parent has no in-memory reservation identifier.
    recovered = WriterAccounting(job, store, state, "fingerprint")
    recovered.reconcile()
    recovered.reconcile()
    assert store.usage(state.id)["cost_usd"] == 8
    assert store.usage(state.id)["reserved_usd"] == 0
    assert store.usage(state.id)["calls"] == 1


def test_settlement_crash_replays_identical_usage_without_double_charge(tmp_path, monkeypatch):
    store, state, job = setup(tmp_path)
    accounting = WriterAccounting(job, store, state, "fingerprint")
    accounting.reserve_remaining(15)
    spend(job, "api-call", 8)
    original = store.settle

    def interrupted(identifier, usage):
        original(identifier, usage)
        raise SystemExit("parent died immediately after settlement")

    monkeypatch.setattr(store, "settle", interrupted)
    with pytest.raises(SystemExit):
        accounting.reconcile()
    monkeypatch.setattr(store, "settle", original)
    WriterAccounting(job, store, state, "fingerprint").reconcile()
    assert store.usage(state.id)["cost_usd"] == 8
    assert store.usage(state.id)["calls"] == 1


def test_idempotent_reservation_recovers_intent_without_second_hold(tmp_path):
    store, state, _ = setup(tmp_path)
    first = store.reserve(state.id, "paper_orchestra", 15, "intent", idempotent=True)
    assert store.reserve(state.id, "paper_orchestra", 15, "intent", idempotent=True) == first
    assert store.usage(state.id)["reserved_usd"] == 15
    with pytest.raises(ConflictError):
        store.reserve(state.id, "paper_orchestra", 14, "intent", idempotent=True)


def test_crash_before_reservation_does_not_strand_writer(tmp_path):
    store, state, job = setup(tmp_path)
    accounting = WriterAccounting(job, store, state, "fingerprint")
    accounting.record["attempts"] = [{"key": "unreserved", "previous_ids": []}]
    accounting.save()
    recovered = WriterAccounting(job, store, state, "fingerprint")
    recovered.reconcile()
    recovered.reserve_remaining(15)
    assert store.usage(state.id)["reserved_usd"] == 15


def test_overrun_records_child_denominator_before_settlement_raises(tmp_path):
    from autoresearch.store import BudgetExceeded

    store, state, job = setup(tmp_path)
    accounting = WriterAccounting(job, store, state, "fingerprint")
    accounting.reserve_remaining(1)
    spend(job, "overrun", 2)
    with pytest.raises(BudgetExceeded, match="reservation"):
        accounting.reconcile()
    usage = store.usage(state.id)
    assert usage["cost_usd"] == 2
    assert usage["model_calls_attempted"] == 1
    assert usage["subordinate_calls"] == 1
    WriterAccounting(job, store, state, "fingerprint").reconcile()
    usage = store.usage(state.id)
    assert usage["cost_usd"] == 2
    assert usage["model_calls_attempted"] == 1
