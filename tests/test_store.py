import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import Usage
from autoresearch.engine import Engine
from autoresearch.privacy import redact
from autoresearch.store import BudgetExceeded, ConflictError, Store


def test_checkpoint_compare_and_swap(tmp_path: Path):
    store = Store(tmp_path)
    a = Engine(store).create("CAS", "Concurrent saves", demo=True)
    b = store.get_run(a.id)
    store.save(a)
    with pytest.raises(ConflictError):
        store.save(b)


def test_atomic_budget_reservation(tmp_path: Path):
    store = Store(tmp_path)
    config = ResearchConfig()
    config.budget.usd = 1.0
    state = Engine(store, config).create("Budget", "Parallel reservations", demo=True)

    def reserve(_: int) -> str:
        try:
            return store.reserve(state.id, "critic", 0.75, "hash")
        except BudgetExceeded:
            return "blocked"

    with ThreadPoolExecutor(2) as pool:
        ids = list(pool.map(reserve, range(2)))
    assert ids.count("blocked") == 1
    call = next(i for i in ids if i != "blocked")
    store.settle(call, Usage(cost_usd=0.1))
    assert store.usage(state.id)["reserved_usd"] == 0
    store.reserve(state.id, "critic", 0.75, "hash")


def test_lease_rejects_other_live_worker(tmp_path: Path):
    store = Store(tmp_path)
    state = Engine(store).create("Lease", "Check coordination", demo=True)
    with store.lease(state.id), pytest.raises(ConflictError):
        with Store(tmp_path).lease(state.id):
            pass


def test_export_metadata_does_not_include_private_objective(tmp_path: Path):
    store = Store(tmp_path / "state")
    state = Engine(store).create("Private title", "Sensitive unpublished content", demo=True)
    target = tmp_path / "export.json"
    store.export_run(state.id, target)
    content = target.read_text()
    assert "Sensitive unpublished content" not in content
    assert "Private title" not in content
    assert "events" not in json.loads(content)


def test_secrets_redacted_from_events_and_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    secret = "TEST_SECRET_VALUE_not_a_real_key"  # noqa: S105 - synthetic redaction fixture
    monkeypatch.setenv("XAI_API_KEY", secret)
    store = Store(tmp_path)
    state = Engine(store).create("Redaction", "Check events", demo=True)
    store.event(state.id, "test", "baseline", {"text": secret, "api_key": secret})
    assert secret not in json.dumps(store.events(state.id))
    assert redact({"api_key_env": "XAI_API_KEY"})["api_key_env"] == "XAI_API_KEY"


def test_nonfinite_config_rejected():
    with pytest.raises(ValueError):
        ResearchConfig.model_validate({"budget": {"usd": float("inf")}})


def test_subordinate_writer_calls_count_once_toward_global_limit(tmp_path: Path):
    config = ResearchConfig()
    config.budget.max_calls = 3
    store = Store(tmp_path)
    state = Engine(store, config).create("Writer accounting", "Count real requests", demo=True)
    parent = store.reserve(state.id, "paper_orchestra", 2, "writer-job")
    for child in ("request-1", "request-2", "request-2"):
        store.event(state.id, "paper_orchestra_api_call", "draft", {"id": child, "cost_usd": 0.1})
    store.settle(parent, Usage(cost_usd=0.2, input_tokens=12))
    store.reserve(state.id, "critic", 0.1, "critic-job")
    with pytest.raises(BudgetExceeded):
        store.reserve(state.id, "critic", 0.1, "over-limit")
    usage = store.usage(state.id)
    assert usage["model_calls_attempted"] == 3
    assert usage["subordinate_calls"] == 2
    assert usage["cost_usd"] == 0.2
    assert usage["input_tokens"] == 12


def test_idempotent_reservation_survives_lost_return_without_second_hold(tmp_path: Path):
    from autoresearch.store import ConflictError

    store = Store(tmp_path)
    state = Engine(store).create("Durable intent", "Recover one reservation", demo=True)
    first = store.reserve(state.id, "paper_orchestra", 2, "durable-key", idempotent=True)
    assert store.reserve(state.id, "paper_orchestra", 2, "durable-key", idempotent=True) == first
    assert store.call_for_request(state.id, "paper_orchestra", "durable-key")["id"] == first
    assert store.usage(state.id)["reserved_usd"] == 2
    with pytest.raises(ConflictError):
        store.reserve(state.id, "paper_orchestra", 3, "durable-key", idempotent=True)
