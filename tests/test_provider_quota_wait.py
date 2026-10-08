"""Opt-in provider quota waiting: offline fakes only, no network or model calls."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ModelSelectionConfig, QuotaWaitConfig, ResearchConfig
from autoresearch.contracts import AgentOutput, AgentRequest, ProviderConfig, Stage
from autoresearch.engine import Engine
from autoresearch.model_inventory import AvailableModel, ModelInventory
from autoresearch.providers import CompatibleProvider, ProviderError, retry_hint_seconds
from autoresearch.quota_wait import next_delay, rate_limit_error, status_message
from autoresearch.store import Store

REQUEST = AgentRequest(run_id="test", stage="novelty", role="critic", system="JSON", prompt="Go")
GOOGLE_429 = [
    {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {"@type": "type.googleapis.com/google.rpc.QuotaFailure"},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"},
            ],
        }
    }
]


def provider_error(status: int, headers=None, body=None, monkeypatch=None) -> ProviderError:
    monkeypatch.setattr("autoresearch.providers.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers or {}, json=body or {})

    config = ProviderConfig(base_url="http://127.0.0.1:9/v1", model="fixture", retries=1)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as caught:
            CompatibleProvider(config, client=client).complete(REQUEST)
    return caught.value


def test_http_429_is_rate_limited_with_retry_after_header(monkeypatch):
    error = provider_error(429, {"retry-after": "120"}, monkeypatch=monkeypatch)
    assert error.rate_limited and error.recoverable
    assert error.retry_after_seconds == 120
    assert error.model == "fixture"
    assert "HTTP 429" in str(error)


def test_http_429_parses_google_retry_delay(monkeypatch):
    error = provider_error(429, body=GOOGLE_429, monkeypatch=monkeypatch)
    assert error.rate_limited
    assert error.retry_after_seconds == 37


@pytest.mark.parametrize("status", [500, 503, 401, 403, 400])
def test_other_failures_are_not_rate_limited(monkeypatch, status):
    error = provider_error(status, {"retry-after": "5"}, GOOGLE_429, monkeypatch)
    assert not error.rate_limited
    assert error.retry_after_seconds is None


GEMINI_OVERLOAD = {
    "error": {
        "code": 503,
        "status": "UNAVAILABLE",
        "message": "This model is currently experiencing high demand. Please try again later.",
    }
}


def test_gemini_overload_503_is_capacity_limited(monkeypatch):
    error = provider_error(503, body=GEMINI_OVERLOAD, monkeypatch=monkeypatch)
    assert error.rate_limited and error.recoverable
    assert "HTTP 503" in str(error)
    listed = provider_error(503, body=[GEMINI_OVERLOAD], monkeypatch=monkeypatch)
    assert listed.rate_limited


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, GEMINI_OVERLOAD),
        (502, GEMINI_OVERLOAD),
        (503, {"error": {"status": "INTERNAL"}}),
        (503, {}),
    ],
)
def test_other_server_errors_never_wait(monkeypatch, status, body):
    assert not provider_error(status, body=body, monkeypatch=monkeypatch).rate_limited


@pytest.mark.parametrize("field", ["code", "type"])
def test_openai_insufficient_quota_429_is_billing_not_a_wait(monkeypatch, field):
    body = {"error": {field: "insufficient_quota", "message": "Check your plan and billing."}}
    error = provider_error(429, {"retry-after": "5"}, body, monkeypatch)
    assert not error.rate_limited
    assert "HTTP 429" in str(error)


def test_transport_failure_is_not_rate_limited(monkeypatch):
    monkeypatch.setattr("autoresearch.providers.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic", request=request)

    config = ProviderConfig(base_url="http://127.0.0.1:9/v1", retries=0)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as caught:
            CompatibleProvider(config, client=client).complete(REQUEST)
    assert caught.value.recoverable and not caught.value.rate_limited


def test_retry_hint_accepts_http_date_and_ignores_garbage():
    later = (datetime.now(UTC) + timedelta(seconds=300)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert 290 <= (retry_hint_seconds({"retry-after": later}, None) or 0) <= 301
    assert retry_hint_seconds({"retry-after": "soon"}, {"error": {"details": "x"}}) is None
    assert retry_hint_seconds({}, {"error": {"details": [{"retryDelay": "1.5s"}]}}) == 1.5


def fallback_setup(tmp_path, monkeypatch, statuses, handlers=None):
    providers = [
        ProviderConfig(name="fixture", model=name, base_url="http://localhost/" + name, retries=0)
        for name in ("cheap", "backup", "third")
    ]
    config = ResearchConfig(
        provider=providers[0],
        model_inventory=ModelInventory(
            models=[AvailableModel(id=p.model, label=p.model, provider=p) for p in providers]
        ),
        allowed_models=["cheap", "backup", "third"],
    )
    config.pipeline.max_agent_repairs = 0
    config.quota_wait.enabled = True
    # Counts provider requests; the optional model_router call is tested separately.
    config.model_selection = ModelSelectionConfig(router="off")
    store = Store(tmp_path / "state")
    state = Engine(store, config, stage_handlers=handlers).create("Synthetic", "Offline")
    seen: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        seen.append(model)
        status = statuses.get(model, 200)
        # A short-window (per-minute) limit: at most the 60 s short-window cap.
        headers = {"retry-after": "45"} if status == 429 else {}
        output = AgentOutput(summary="Checked", confidence=1, limitations=["Synthetic"])
        return httpx.Response(
            status,
            headers=headers,
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
    return store, state, config, seen, statuses


def test_fallback_keeps_flag_only_when_every_route_is_rate_limited(tmp_path, monkeypatch):
    statuses = dict.fromkeys(("cheap", "backup", "third"), 429)
    store, state, config, seen, _ = fallback_setup(tmp_path, monkeypatch, statuses)
    runner = AgentRunner(store, config)
    with pytest.raises(ProviderError) as caught:
        runner._one(state, "limitations", {}, 0)
    assert caught.value.rate_limited and caught.value.retry_after_seconds == 45
    # Every model is cooling down: the synthetic error must still say "rate limited".
    with pytest.raises(ProviderError, match="cooling down") as cooling:
        runner._one(state, "limitations", {}, 0)
    assert cooling.value.rate_limited and cooling.value.retry_after_seconds == 45
    assert len(seen) == 3
    failures = [e for e in store.events(state.id) if e["kind"] == "agent_provider_failed"]
    assert all(e["payload"]["rate_limited"] for e in failures)


def test_fallback_hint_is_unknown_when_any_limited_route_has_none(tmp_path, monkeypatch):
    statuses = dict.fromkeys(("cheap", "backup", "third"), 429)
    store, state, config, seen, _ = fallback_setup(tmp_path, monkeypatch, statuses)
    runner = AgentRunner(store, config)
    with pytest.raises(ProviderError):
        runner._one(state, "limitations", {}, 0)
    runner._rate_limited[next(iter(runner._rate_limited))] = None
    with pytest.raises(ProviderError, match="cooling down") as cooling:
        runner._one(state, "limitations", {}, 0)
    assert cooling.value.rate_limited and cooling.value.retry_after_seconds is None


def test_mixed_rate_limit_and_server_error_is_not_quota_wait(tmp_path, monkeypatch):
    statuses = {"cheap": 503, "backup": 429, "third": 429}
    store, state, config, _, _ = fallback_setup(tmp_path, monkeypatch, statuses)
    with pytest.raises(ProviderError) as caught:
        AgentRunner(store, config)._one(state, "limitations", {}, 0)
    assert not caught.value.rate_limited


def test_wrapped_rate_limit_is_found_but_suppressed_context_is_not():
    limited = ProviderError("HTTP 429", rate_limited=True)
    try:
        try:
            raise limited
        except ProviderError as exc:
            raise ValueError("stage wrapper") from exc
    except ValueError as wrapped:
        assert rate_limit_error(wrapped) is limited
    try:
        try:
            raise limited
        except ProviderError:
            raise ValueError("unrelated") from None
    except ValueError as suppressed:
        assert rate_limit_error(suppressed) is None
    assert rate_limit_error(ProviderError("HTTP 503", recoverable=True)) is None


def test_backoff_respects_hint_and_cap():
    config = QuotaWaitConfig(enabled=True, initial_seconds=60, max_interval_seconds=600)
    assert [next_delay(config, n, None) for n in range(5)] == [60, 120, 240, 480, 600]
    assert next_delay(config, 0, 300) == 300
    assert next_delay(config, 0, 10_000) == 600
    with pytest.raises(ValueError):
        QuotaWaitConfig(initial_seconds=100, max_interval_seconds=10)


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
    return current


def engine_with(tmp_path, outcomes, *, enabled=True, **quota):
    """Each handler call consumes one outcome: an exception to raise, or None for success."""
    store = Store(tmp_path)
    calls: list[int] = []

    def handler(state, config, runner):
        calls.append(1)
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome
        state.limitations = ["Synthetic limitation"]
        state.stage = Stage.VERIFY_LIMITATIONS

    config = ResearchConfig()
    config.quota_wait = QuotaWaitConfig(enabled=enabled, **quota)
    engine = Engine(store, config, stage_handlers={Stage.LIMITATIONS: handler})
    state = engine.create("Quota wait", "Synthetic fixture", demo=True)
    return store, engine, state, calls


def limited(hint: float | None = None) -> ProviderError:
    return ProviderError(
        "Provider failed after retries (HTTP 429)",
        recoverable=True,
        rate_limited=True,
        retry_after_seconds=hint,
        model="gemini-fixture",
    )


def test_disabled_keeps_existing_blocked_behavior(tmp_path, clock):
    store, engine, state, calls = engine_with(tmp_path, [limited()], enabled=False)
    after = engine.step(state.id)
    assert after.status == "blocked" and "HTTP 429" in after.error
    assert not after.quota_wait_until
    assert not [e for e in store.events(state.id) if e["kind"] == "provider_quota_wait"]


def test_non_rate_limit_failure_blocks_even_when_enabled(tmp_path, clock):
    error = ProviderError("Provider failed after retries (HTTP 503)", recoverable=True)
    store, engine, state, calls = engine_with(tmp_path, [error])
    assert engine.step(state.id).status == "blocked"


def test_rate_limit_waits_then_resumes_and_clears_counter(tmp_path, clock):
    store, engine, state, calls = engine_with(tmp_path, [limited(30), limited(), None])
    start = clock.value
    after = engine.step(state.id)
    assert after.status == "waiting" and after.error == ""
    assert datetime.fromisoformat(after.quota_wait_until) == start + timedelta(seconds=60)
    assert after.quota_wait_attempts == 1
    event = [e for e in store.events(state.id) if e["kind"] == "provider_quota_wait"][-1]
    assert event["payload"]["model"] == "gemini-fixture"
    assert event["payload"]["wait_seconds"] == 60
    assert event["payload"]["retry_after_seconds"] == 30
    assert event["payload"]["next_attempt_at"] == after.quota_wait_until
    assert "HTTP 429" in event["payload"]["reason"]

    # Before the not-before time no handler (and thus no provider call) runs.
    clock.advance(59)
    version = store.get_run(state.id).version
    assert engine.step(state.id).status == "waiting"
    assert len(calls) == 1
    assert store.get_run(state.id).version == version

    clock.advance(2)
    second = engine.step(state.id)
    assert len(calls) == 2
    assert second.status == "waiting" and second.quota_wait_attempts == 2
    assert second.quota_wait_seconds == 180
    assert datetime.fromisoformat(second.quota_wait_until) == clock.value + timedelta(seconds=120)

    clock.advance(121)
    done = engine.step(state.id)
    assert len(calls) == 3
    assert done.status == "ready" and done.stage == Stage.VERIFY_LIMITATIONS
    assert (done.quota_wait_until, done.quota_wait_attempts, done.quota_wait_seconds) == (
        "",
        0,
        0,
    )
    kinds = [e["kind"] for e in store.events(state.id)]
    assert kinds.count("provider_quota_wait") == 2  # history is never removed


def test_elapsed_wait_then_coding_pending_does_not_busy_loop(tmp_path, clock, monkeypatch):
    """Regression: a stale past not-before time used to skip the ordinary poll sleep."""
    from autoresearch.coding import CodingPending

    outcomes = [limited()] + [CodingPending("synthetic pending job")] * 5
    store, engine, state, calls = engine_with(tmp_path, outcomes)
    engine.step(state.id)
    clock.advance(61)
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    monkeypatch.setattr("autoresearch.engine.time.sleep", sleep)
    after = engine.run(state.id, max_steps=3)
    assert len(calls) == 4  # one 429, then three pending steps
    assert after.status == "waiting" and after.quota_wait_until == ""
    assert after.quota_wait_attempts == 1  # counters persist until a successful step
    assert len(sleeps) == 3 and all(0 < s <= 10 for s in sleeps)
    assert status_message(after.status, after.quota_wait_until) == ""


def test_quota_wait_event_records_the_stage_that_failed(tmp_path, clock):
    store = Store(tmp_path)

    def handler(state, config, runner):
        state.stage = Stage.VERIFY_LIMITATIONS
        raise limited()

    config = ResearchConfig()
    config.quota_wait.enabled = True
    engine = Engine(store, config, stage_handlers={Stage.LIMITATIONS: handler})
    state = engine.create("Quota wait", "Synthetic fixture", demo=True)
    engine.step(state.id)
    event = [e for e in store.events(state.id) if e["kind"] == "provider_quota_wait"][-1]
    assert event["payload"]["stage"] == Stage.LIMITATIONS.value


def test_wrapped_rate_limit_from_stage_handler_waits(tmp_path, clock):
    try:
        raise ValueError("specialist failed") from limited()
    except ValueError as wrapped:
        error = wrapped
    store, engine, state, calls = engine_with(tmp_path, [error])
    assert engine.step(state.id).status == "waiting"


def test_cumulative_limit_falls_back_to_blocked(tmp_path, clock):
    store, engine, state, calls = engine_with(
        tmp_path,
        [limited(), limited(), limited()],
        initial_seconds=60,
        max_interval_seconds=3600,
        max_total_seconds=200,
    )
    assert engine.step(state.id).status == "waiting"  # 60 s scheduled
    clock.advance(61)
    assert engine.step(state.id).status == "waiting"  # 180 s scheduled
    clock.advance(121)
    after = engine.step(state.id)  # next 240 s would exceed 200 s
    assert after.status == "blocked"
    assert "HTTP 429" in after.error and "Stopped waiting for provider quota" in after.error
    assert after.quota_wait_attempts == 0 and not after.quota_wait_until
    error = [e for e in store.events(state.id) if e["kind"] == "stage_error"][-1]
    assert error["payload"]["quota_wait_exhausted"] is True
    assert error["payload"]["quota_wait_attempts"] == 2
    # Blocked still requires an explicit resume; a watch loop does not retry it.
    engine.step(state.id)
    assert len(calls) == 3


def test_pause_is_honored_while_waiting_and_resume_does_not_probe_early(
    tmp_path, clock, monkeypatch
):
    store, engine, state, calls = engine_with(tmp_path, [limited(), None])
    engine.step(state.id)
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)
        if len(sleeps) == 2:
            engine.pause(state.id)

    monkeypatch.setattr("autoresearch.engine.time.sleep", sleep)
    paused = engine.run(state.id)
    assert paused.status == "paused"
    assert sleeps == [10, 10]  # bounded chunks, not one long sleep or a busy loop
    assert len(calls) == 1
    resumed = engine.resume(state.id)
    assert resumed.status == "waiting"
    assert engine.step(state.id).status == "waiting"
    assert len(calls) == 1
    # The first step only observes the wait; the run loop then sleeps until it ends.
    final = engine.run(state.id, max_steps=2)
    assert final.status == "ready" and len(calls) == 2
    assert sum(sleeps) >= 60


def test_run_sleeps_until_not_before_and_continues(tmp_path, clock, monkeypatch):
    store, engine, state, calls = engine_with(tmp_path, [limited(25), None])
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    monkeypatch.setattr("autoresearch.engine.time.sleep", sleep)
    after = engine.run(state.id, max_steps=2)
    assert len(calls) == 2
    assert after.stage == Stage.VERIFY_LIMITATIONS
    assert sum(sleeps) == pytest.approx(60)
    assert max(sleeps) <= 10


def test_wall_clock_budget_stops_a_waiting_run(tmp_path, clock, monkeypatch):
    store, engine, state, calls = engine_with(tmp_path, [limited(), None])
    store.update_budget(state.id, wall_seconds=30)
    assert engine.step(state.id).status == "waiting"
    monkeypatch.setattr("autoresearch.engine.time.sleep", clock.advance)
    after = engine.run(state.id)
    assert after.status == "budget_exhausted"
    assert "waiting for provider quota" in after.error
    assert len(calls) == 1


def test_call_budget_still_applies_to_quota_probes(tmp_path, clock, monkeypatch):
    def handler(state, config, runner):
        runner._one(state, "limitations", {}, 0)

    handler.behavior_identity = lambda: {"fixture": "quota-probe-v1"}  # type: ignore[attr-defined]
    handlers = {Stage.LIMITATIONS: handler}
    statuses = dict.fromkeys(("cheap", "backup", "third"), 429)
    store, state, config, seen, _ = fallback_setup(tmp_path, monkeypatch, statuses, handlers)
    store.update_budget(state.id, max_calls=4)
    engine = Engine(store, stage_handlers=handlers)
    first = engine.step(state.id)
    assert first.status == "waiting", first.error
    assert len(seen) == 3
    assert first.quota_wait_seconds == 60  # the 60 s initial wait exceeds the 45 s hint
    clock.advance(61)
    second = engine.step(state.id)
    assert second.status == "budget_exhausted"
    assert len(seen) == 4
    assert store.usage(state.id)["calls"] == 4


def test_status_text_is_literal():
    until = datetime(2026, 1, 1, 9, 5, tzinfo=UTC)
    local = until.astimezone()
    text = status_message("waiting", until.isoformat(), current=until - timedelta(minutes=1))
    assert text == f"Waiting for provider quota; next attempt at {local:%H:%M}"
    # An elapsed time is never shown as a pending attempt.
    assert status_message("waiting", until.isoformat(), current=until) == ""
    assert status_message("ready", until.isoformat()) == ""
    assert status_message("waiting", "") == ""
    tomorrow = status_message("waiting", until.isoformat(), current=until - timedelta(days=2))
    assert f"{local:%Y-%m-%d}" in tomorrow


def test_metis_status_prints_quota_wait(capsys, monkeypatch):
    from autoresearch.terminal_style import print_status

    monkeypatch.setenv("NO_COLOR", "1")
    until = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    run = {
        "id": "fixture",
        "title": "Synthetic",
        "objective": "Offline",
        "stage": "limitations",
        "status": "waiting",
        "quota_wait_until": until,
    }
    print_status({"run": run, "usage": {}}, "charcoal")
    assert "Waiting for provider quota; next attempt at" in capsys.readouterr().out
