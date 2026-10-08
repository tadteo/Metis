"""Quota-aware routing: long-window 429s, persisted per-model exhaustion and size guards.

All transports are offline mocks; no model or network request is made.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from autoresearch.agents import AgentRunner, quota_key
from autoresearch.config import QuotaWaitConfig, ResearchConfig
from autoresearch.contracts import (
    AgentOutput,
    AgentRequest,
    ModelQuotaExhaustion,
    ProviderConfig,
    RunState,
    Stage,
)
from autoresearch.engine import Engine
from autoresearch.memory import research_view
from autoresearch.model_inventory import AvailableModel, ModelInventory
from autoresearch.providers import (
    UNKNOWN_RESET_SECONDS,
    CompatibleProvider,
    ProviderError,
    _reset_seconds,
    quota_window,
)
from autoresearch.quota_wait import prune_exhaustion, reset_delay
from autoresearch.store import Store

REQUEST = AgentRequest(run_id="test", stage="novelty", role="critic", system="JSON", prompt="Go")
DAILY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"


def google_429(quota_id: str, value: str, delay: float | None) -> list[dict]:
    details: list[dict] = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "quotaMetric": "generativelanguage.googleapis.com/requests",
                    "quotaId": quota_id,
                    "quotaDimensions": {"location": "global", "model": "fixture"},
                    "quotaValue": value,
                }
            ],
        }
    ]
    if delay is not None:
        details.append(
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": f"{delay}s"}
        )
    return [{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": details}}]


def call(monkeypatch, response: httpx.Response, retries: int = 8):
    sleeps: list[float] = []
    monkeypatch.setattr("autoresearch.providers.time.sleep", sleeps.append)
    sent: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(1)
        return response

    config = ProviderConfig(base_url="http://127.0.0.1:9/v1", model="fixture", retries=retries)
    provider = CompatibleProvider(
        config, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ProviderError) as caught:
        provider.complete(REQUEST)
    return caught.value, len(sent), sleeps, provider._estimate(REQUEST)


# Provider classification ------------------------------------------------------------


def test_daily_quota_429_stops_after_one_attempt(monkeypatch):
    before = datetime.now(UTC)
    response = httpx.Response(429, json=google_429(DAILY, "20", 85101))
    error, sent, sleeps, estimate = call(monkeypatch, response)
    assert sent == 1 and sleeps == []
    assert error.rate_limited and error.recoverable
    assert error.retry_after_seconds == 85101
    until = datetime.fromisoformat(error.quota_exhausted_until)
    assert before + timedelta(seconds=85100) < until < before + timedelta(seconds=85200)
    assert error.quota["quota_id"] == DAILY and error.quota["quota_value"] == "20"
    assert error.quota["window"] == "long"
    assert "quota exhausted" in str(error)
    # One unanswered attempt is charged once, at the conservative estimate.
    assert error.usage.cost_usd == pytest.approx(estimate.cost_usd)
    assert error.usage.estimated


def test_daily_quota_without_retry_info_uses_documented_reprobe_delay(monkeypatch):
    response = httpx.Response(429, json=google_429(DAILY, "20", None))
    error, sent, _, _ = call(monkeypatch, response)
    assert sent == 1 and error.retry_after_seconds == UNKNOWN_RESET_SECONDS
    assert error.quota_exhausted_until


def test_long_retry_delay_alone_is_long_window(monkeypatch):
    response = httpx.Response(429, headers={"retry-after": "7200"}, json={})
    error, sent, _, _ = call(monkeypatch, response)
    assert sent == 1 and error.retry_after_seconds == 7200 and error.quota_exhausted_until


def test_per_minute_429_keeps_bounded_retries(monkeypatch):
    response = httpx.Response(429, json=google_429(MINUTE, "10", 29))
    error, sent, sleeps, estimate = call(monkeypatch, response, retries=2)
    assert sent == 3 and sleeps == [29, 29]
    assert error.rate_limited and error.retry_after_seconds == 29
    assert error.quota_exhausted_until == "" and error.quota == {}
    assert error.usage.cost_usd == pytest.approx(3 * estimate.cost_usd)


def test_openai_style_reset_headers():
    long = {"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "2h0m0s"}
    window, reset, quota = quota_window(long, {}, None)
    assert (window, reset) == ("long", 7200) and quota["quota_id"] == "x-ratelimit-requests"
    short = {"x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "20s"}
    assert quota_window(short, {}, None)[:2] == ("short", 20)
    # Remaining capacity means the reset header says nothing about this failure.
    assert quota_window({"x-ratelimit-reset-requests": "9h"}, {}, None) == ("short", None, {})
    assert _reset_seconds("6m0s") == 360 and _reset_seconds("20ms") == 0.02
    assert _reset_seconds("1h2m3.5s") == 3723.5 and _reset_seconds("soon") is None


# Routing helpers ----------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.value = datetime.now(UTC)

    def __call__(self) -> str:
        return self.value.isoformat()

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch) -> Clock:
    current = Clock()
    monkeypatch.setattr("autoresearch.engine.now", current)
    monkeypatch.setattr("autoresearch.agents.now", current)
    return current


def routed(tmp_path, monkeypatch, responses, *, models=("cheap", "backup", "third"), **quota):
    """Live-mode run over a frozen pool; ``responses[model]`` is a status or a callable."""
    providers = [
        ProviderConfig(
            name="fixture",
            model=name,
            base_url="http://localhost/" + name,
            retries=8,
            max_output_tokens=256,
            # Distinct prices fix the cost order: cheap < backup < third < fourth.
            input_per_million=1.0 + position,
        )
        for position, name in enumerate(models)
    ]
    config = ResearchConfig(
        provider=providers[0],
        model_inventory=ModelInventory(
            models=[AvailableModel(id=p.model, label=p.model, provider=p) for p in providers]
        ),
        allowed_models=list(models),
    )
    config.pipeline.max_agent_repairs = 0
    config.quota_wait = QuotaWaitConfig(**{"enabled": True, **quota})
    monkeypatch.setattr("autoresearch.providers.time.sleep", lambda _: None)
    seen: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        seen.append(model)
        outcome = responses.get(model, 200)
        if callable(outcome):
            return outcome(request)
        if outcome != 200:
            return httpx.Response(outcome, json={})
        output = AgentOutput(summary="Checked", confidence=1, limitations=["Synthetic"])
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": output.model_dump_json()}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(
        "autoresearch.agents.CompatibleProvider",
        lambda cfg: CompatibleProvider(
            cfg, client=httpx.Client(transport=httpx.MockTransport(transport))
        ),
    )

    def handler(state, config, runner):
        runner._one(state, "limitations", {}, 0)
        state.limitations = ["Synthetic limitation"]
        # Alternate along declared edges so consecutive steps are different stages.
        state.stage = (
            Stage.VERIFY_LIMITATIONS if state.stage == Stage.LIMITATIONS else Stage.LIMITATIONS
        )

    handler.behavior_identity = lambda: {"fixture": "quota-routing-v1"}  # type: ignore[attr-defined]
    handlers = {Stage.LIMITATIONS: handler, Stage.VERIFY_LIMITATIONS: handler}
    store = Store(tmp_path / "state")
    state = Engine(store, config, stage_handlers=handlers).create("Synthetic", "Offline")
    return store, state, config, seen, handlers


def daily(delay: float):
    return lambda request: httpx.Response(429, json=google_429(DAILY, "20", delay))


def events(store, run_id, kind):
    return [e["payload"] for e in store.events(run_id) if e["kind"] == kind]


# Persisted per-model exhaustion ---------------------------------------------------------


def test_exhausted_model_is_skipped_across_steps_and_restarts(tmp_path, monkeypatch, clock):
    store, state, config, seen, handlers = routed(tmp_path, monkeypatch, {"cheap": daily(85101)})
    first = Engine(store, stage_handlers=handlers).step(state.id)
    assert first.status == "ready", first.error
    assert seen == ["cheap", "backup"]  # one request to the exhausted model, not nine
    record = first.model_quota_exhausted[quota_key(config.provider)]
    assert record.model == "cheap" and record.quota_id == DAILY and record.quota_value == "20"
    [exhausted] = events(store, state.id, "model_quota_exhausted")
    assert exhausted["model"] == "cheap" and exhausted["until"] == record.until
    # The record is part of the persisted run state.
    assert store.get_run(state.id).model_quota_exhausted.keys() == {quota_key(config.provider)}

    # A new engine (restart) and the next stage skip the exhausted model entirely.
    second = Engine(store, stage_handlers=handlers).step(state.id)
    assert second.status == "ready", second.error
    assert seen == ["cheap", "backup", "backup"]
    fallback = events(store, state.id, "provider_fallback")[-1]
    assert fallback["to_model"] == "backup" and "quota exhausted until" in fallback["reason"]

    # After the reset the record is pruned and the model is eligible again.
    clock.advance(85200)
    store, state2, config2, seen2, handlers2 = routed(tmp_path / "again", monkeypatch, {})
    runner = AgentRunner(store, config2)
    state2.model_quota_exhausted[quota_key(config2.provider)] = record
    runner._one(state2, "limitations", {}, 0)
    assert seen2 == ["cheap"]
    prune_exhaustion(state2, clock.value)
    assert state2.model_quota_exhausted == {}


def test_exhausted_models_free_their_alternative_slot(tmp_path, monkeypatch, clock):
    models = ("cheap", "backup", "third", "fourth")
    exhausted = dict.fromkeys(models[:3], daily(9000))
    store, state, config, seen, _ = routed(tmp_path, monkeypatch, exhausted, models=models)
    with pytest.raises(ProviderError) as caught:
        AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen == ["cheap", "backup", "third"] and caught.value.quota_exhausted_until
    # Exhausted models no longer occupy the two alternative slots: the next model in
    # cost order is reached instead of the run waiting.
    AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen[3:] == ["fourth"]


def test_all_exhausted_waits_until_earliest_reset_without_probing(tmp_path, monkeypatch, clock):
    responses = {"cheap": daily(50000), "backup": daily(7200), "third": daily(86000)}
    store, state, config, seen, handlers = routed(
        tmp_path, monkeypatch, responses, max_interval_seconds=3600
    )
    engine = Engine(store, stage_handlers=handlers)
    first = engine.step(state.id)
    assert first.status == "waiting", first.error
    assert seen == ["cheap", "backup", "third"]  # one attempt each
    assert len(first.model_quota_exhausted) == 3
    wait = events(store, state.id, "provider_quota_wait")[-1]
    earliest = datetime.fromisoformat(wait["quota_exhausted_until"])
    assert abs((earliest - clock.value).total_seconds() - 7200) < 5
    assert wait["wait_seconds"] == 3600  # capped by max_interval_seconds

    # The capped wake-up sends no request: every permitted model is still exhausted.
    clock.advance(3601)
    second = engine.step(state.id)
    assert second.status == "waiting" and seen == ["cheap", "backup", "third"]
    assert events(store, state.id, "model_quota_skipped")
    remaining = events(store, state.id, "provider_quota_wait")[-1]["wait_seconds"]
    assert 3590 < remaining < 3600  # the remainder up to the earliest reset

    # At the earliest reset a single probe reaches the model that reset first.
    responses["backup"] = 200
    clock.advance(remaining + 1)
    third = engine.step(state.id)
    assert third.status == "ready", third.error
    assert seen[3:] == ["backup"]
    assert set(third.model_quota_exhausted) == {
        quota_key(config.model_inventory.models[0].provider),
        quota_key(config.model_inventory.models[2].provider),
    }


def test_wait_resumes_at_reset_when_within_interval(tmp_path, monkeypatch, clock):
    responses = {"cheap": daily(7200), "backup": daily(9000), "third": daily(8000)}
    store, state, _, _, handlers = routed(
        tmp_path, monkeypatch, responses, max_interval_seconds=86400
    )
    first = Engine(store, stage_handlers=handlers).step(state.id)
    moment = datetime.fromisoformat(first.quota_wait_until)
    assert abs((moment - clock.value).total_seconds() - 7200) < 5


def test_quota_disabled_blocks_when_all_exhausted(tmp_path, monkeypatch, clock):
    responses = dict.fromkeys(("cheap", "backup", "third"), daily(7200))
    store, state, _, seen, handlers = routed(tmp_path, monkeypatch, responses, enabled=False)
    after = Engine(store, stage_handlers=handlers).step(state.id)
    assert after.status == "blocked" and "quota exhausted" in after.error
    assert len(seen) == 3 and len(after.model_quota_exhausted) == 3


# Protected routes ------------------------------------------------------------------------


@pytest.mark.parametrize("enabled", [True, False])
def test_protected_route_is_never_swapped_when_exhausted(tmp_path, monkeypatch, clock, enabled):
    store, state, config, seen, _ = routed(tmp_path, monkeypatch, {})
    config.role_panels["limitations"] = [config.provider]
    until = clock.value + timedelta(hours=5)
    state.model_quota_exhausted[quota_key(config.provider)] = ModelQuotaExhaustion(
        model="cheap", until=until.isoformat()
    )
    with pytest.raises(ProviderError) as caught:
        AgentRunner(store, config)._one(state, "limitations", {}, 0)
    error = caught.value
    assert seen == [] and error.rate_limited and not error.recoverable
    assert "not swapped" in str(error)
    assert datetime.fromisoformat(error.quota_exhausted_until) == until
    assert events(store, state.id, "model_quota_skipped")[-1]["protected"] is True
    # The engine then waits (opt-in) or blocks; it never picks another model.
    cfg = QuotaWaitConfig(enabled=True, max_interval_seconds=86400)
    assert reset_delay(cfg, error.quota_exhausted_until, clock()) == pytest.approx(5 * 3600)


# Probes and accounting ---------------------------------------------------------------


def test_probe_after_wait_uses_one_attempt_and_one_charge(tmp_path, monkeypatch, clock):
    minute = lambda request: httpx.Response(  # noqa: E731
        429, json=google_429(MINUTE, "10", 20)
    )
    store, state, config, seen, handlers = routed(
        tmp_path, monkeypatch, {"cheap": minute}, models=("cheap",)
    )
    reserved: list[float] = []
    original = store.reserve

    def reserve(run_id, role, maximum, *args, **kwargs):
        reserved.append(maximum)
        return original(run_id, role, maximum, *args, **kwargs)

    monkeypatch.setattr(store, "reserve", reserve)
    engine = Engine(store, stage_handlers=handlers)
    first = engine.step(state.id)
    assert first.status == "waiting" and len(seen) == 9  # short window: bounded retries
    cost = store.usage(state.id)["cost_usd"]
    assert first.model_quota_exhausted == {}

    clock.advance(61)
    second = engine.step(state.id)
    assert second.status == "waiting" and len(seen) == 10  # the probe is one request
    # The probe prompt differs by a few bytes (state counters), hence the tolerance.
    assert reserved[1] == pytest.approx(reserved[0] / 9, rel=1e-3)
    assert store.usage(state.id)["cost_usd"] == pytest.approx(cost * 10 / 9, rel=1e-3)
    assert store.usage(state.id)["calls"] == 2 and store.usage(state.id)["reserved_usd"] == 0


def test_daily_exhaustion_is_charged_once_per_attempt(tmp_path, monkeypatch, clock):
    store, state, config, seen, _ = routed(
        tmp_path, monkeypatch, {"cheap": daily(85101)}, models=("cheap",)
    )
    with pytest.raises(ProviderError) as caught:
        AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen == ["cheap"] and caught.value.quota_exhausted_until
    failed = events(store, state.id, "agent_provider_failed")[-1]
    assert store.usage(state.id)["cost_usd"] == pytest.approx(failed["usage"]["cost_usd"])
    assert store.usage(state.id)["calls"] == 1
    # The next call sends nothing and charges nothing.
    with pytest.raises(ProviderError, match="no other permitted model"):
        AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen == ["cheap"] and store.usage(state.id)["calls"] == 1


# Optional pre-dispatch size guard ----------------------------------------------------


class LimitedModel(AvailableModel):
    """Stand-in for optional inventory metadata (see docs/model-routing.md)."""

    context_window_tokens: int | None = None
    tokens_per_minute: int | None = None


def limit(config: ResearchConfig, **limits: dict[str, int]) -> None:
    assert config.model_inventory is not None
    config.model_inventory.models = [
        LimitedModel(**entry.model_dump(), **limits.get(entry.id, {}))
        for entry in config.model_inventory.models
    ]


def test_oversized_request_skips_a_model_that_cannot_accept_it(tmp_path, monkeypatch, clock):
    store, state, config, seen, _ = routed(tmp_path, monkeypatch, {})
    limit(config, cheap={"tokens_per_minute": 10}, backup={"context_window_tokens": 1_000_000})
    AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen == ["backup"]
    [oversized] = events(store, state.id, "model_request_oversized")
    assert oversized["model"] == "cheap" and oversized["tokens_per_minute"] == 10
    assert store.usage(state.id)["calls"] == 1  # nothing reserved for the skipped model


def test_no_model_fits_blocks_instead_of_waiting(tmp_path, monkeypatch, clock):
    store, state, config, seen, _ = routed(tmp_path, monkeypatch, {})
    small = {"context_window_tokens": 10}
    limit(config, cheap=small, backup=small, third=small)
    with pytest.raises(ProviderError, match="every permitted model") as caught:
        AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen == [] and not caught.value.rate_limited and not caught.value.recoverable
    assert store.usage(state.id)["calls"] == 0


def test_size_guard_is_inactive_without_metadata(tmp_path, monkeypatch, clock):
    store, state, config, seen, _ = routed(tmp_path, monkeypatch, {})
    AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen == ["cheap"] and not events(store, state.id, "model_request_oversized")


# Prompt stability and helpers ------------------------------------------------------------


def test_exhaustion_records_never_reach_model_prompts():
    state = RunState(id="0123456789ab", title="t", objective="o")
    state.model_quota_exhausted["k"] = ModelQuotaExhaustion(model="m", until="2026-10-09T00:00Z")
    assert "model_quota_exhausted" not in research_view(state)


def test_reset_delay_is_bounded():
    cfg = QuotaWaitConfig(enabled=True, max_interval_seconds=3600)
    current = "2026-10-08T00:00:00+00:00"
    assert reset_delay(cfg, "2026-10-08T00:10:00+00:00", current) == 600
    assert reset_delay(cfg, "2026-10-09T00:00:00+00:00", current) == 3600
    assert reset_delay(cfg, "2026-10-07T00:00:00+00:00", current) == 1
    assert reset_delay(cfg, "", current) is None


# Review follow-ups ----------------------------------------------------------------------


def minute_429(delay: float = 20):
    return httpx.Response(429, json=google_429(MINUTE, "10", delay))


def ok_response():
    output = AgentOutput(summary="Checked", confidence=1, limitations=["Synthetic"])
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": output.model_dump_json()}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        },
    )


def test_probe_flag_is_one_shot(tmp_path, monkeypatch, clock):
    queue = [minute_429(), minute_429(), ok_response()]
    store, state, config, seen, _ = routed(
        tmp_path, monkeypatch, {"cheap": lambda request: queue.pop(0)}, models=("cheap",)
    )
    runner = AgentRunner(store, config)
    runner.single_attempt = True
    with pytest.raises(ProviderError):
        runner._one(state, "limitations", {}, 0)
    assert len(seen) == 1 and runner.single_attempt is False
    # Later calls in the same step use the configured bounded retries again.
    runner._one(state, "limitations", {"call": 2}, 0)
    assert len(seen) == 3


def test_command_role_ignores_exhausted_nominal_model(tmp_path, monkeypatch, clock):
    from autoresearch.contracts import AgentResponse, Usage

    store, state, config, seen, _ = routed(tmp_path, monkeypatch, {}, models=("cheap",))
    config.role_commands["limitations"] = ["/bin/true"]
    config.role_command_max_cost_usd["limitations"] = 1.0
    state.model_quota_exhausted[quota_key(config.provider)] = ModelQuotaExhaustion(
        model="cheap", until=(clock.value + timedelta(hours=5)).isoformat()
    )
    runner = AgentRunner(store, config)
    output = AgentOutput(summary="Adapter", confidence=1, limitations=["Synthetic"])
    monkeypatch.setattr(
        runner,
        "_command",
        lambda *args: AgentResponse(
            data=output.model_dump(), usage=Usage(), model="adapter", provider="command"
        ),
    )
    assert runner._one(state, "limitations", {}, 0).summary == "Adapter"
    assert seen == [] and not events(store, state.id, "model_quota_skipped")


def test_daily_quota_with_short_retry_delay_waits_at_least_reprobe_delay(monkeypatch):
    response = httpx.Response(429, json=google_429(DAILY, "20", 10))
    error, sent, _, _ = call(monkeypatch, response)
    assert sent == 1 and error.retry_after_seconds == UNKNOWN_RESET_SECONDS


def test_single_route_daily_429_reports_earliest_pool_reset(tmp_path, monkeypatch, clock):
    store, state, config, seen, _ = routed(
        tmp_path, monkeypatch, {"cheap": daily(85101)}, models=("cheap", "backup")
    )
    soon = clock.value + timedelta(seconds=600)
    backup = config.model_inventory.models[1].provider
    state.model_quota_exhausted[quota_key(backup)] = ModelQuotaExhaustion(
        model="backup", until=soon.isoformat()
    )
    with pytest.raises(ProviderError) as caught:
        AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert seen == ["cheap"]
    assert datetime.fromisoformat(caught.value.quota_exhausted_until) == soon
    assert 590 < (caught.value.retry_after_seconds or 0) <= 600


def test_parallel_agents_record_one_exhaustion(tmp_path, monkeypatch, clock):
    from concurrent.futures import ThreadPoolExecutor

    store, state, config, seen, _ = routed(tmp_path, monkeypatch, {"cheap": daily(85101)})
    runner = AgentRunner(store, config)
    with ThreadPoolExecutor(max_workers=3) as pool:
        outputs = list(
            pool.map(lambda index: runner._one(state, "limitations", {}, index), range(3))
        )
    assert all(output.summary == "Checked" for output in outputs)
    # Concurrent agents may each spend one request before the first records it.
    assert 1 <= seen.count("cheap") <= 3
    assert list(state.model_quota_exhausted) == [quota_key(config.provider)]


def test_short_window_hint_above_initial_wait_is_honored(tmp_path, monkeypatch, clock):
    store, state, _, seen, handlers = routed(
        tmp_path,
        monkeypatch,
        {"cheap": lambda request: minute_429(50)},
        models=("cheap",),
        initial_seconds=30,
    )
    first = Engine(store, stage_handlers=handlers).step(state.id)
    assert first.status == "waiting" and first.quota_wait_seconds == 50
    assert first.model_quota_exhausted == {}


def test_resume_can_clear_recorded_exhaustion(tmp_path, monkeypatch, clock):
    responses = dict.fromkeys(("cheap", "backup", "third"), daily(7200))
    store, state, _, seen, handlers = routed(tmp_path, monkeypatch, responses)
    engine = Engine(store, stage_handlers=handlers)
    assert engine.step(state.id).status == "waiting"
    kept = engine.resume(state.id)
    assert kept.status == "waiting" and len(kept.model_quota_exhausted) == 3
    cleared = engine.resume(state.id, clear_quota=True)
    assert cleared.status == "ready" and cleared.model_quota_exhausted == {}
    assert cleared.quota_wait_until == ""
    assert events(store, state.id, "model_quota_cleared")[-1]["models"] == [
        "backup",
        "cheap",
        "third",
    ]
