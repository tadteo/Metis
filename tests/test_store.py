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


def test_provider_cache_coverage_excludes_unreported_and_historical_calls(tmp_path):
    store = Store(tmp_path)
    state = Engine(store).create("Cache receipts", "Public synthetic fixture", demo=True)
    for inputs, cached in [(1000, 800), (1000, 0), (9000, None)]:
        call = store.reserve(state.id, "critic", 1, f"{inputs}-{cached}")
        store.settle(call, Usage(input_tokens=inputs, cached_input_tokens=cached, cost_usd=0.1))
    usage = store.usage(state.id)
    assert usage["input_tokens"] == 11000
    assert usage["cached_input_tokens"] == 800
    assert usage["cache_reported_input_tokens"] == 2000
    assert usage["cost_usd"] == pytest.approx(0.3)
