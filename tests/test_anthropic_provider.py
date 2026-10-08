"""Native Anthropic adapter: request shape, streaming, refusals, accounting and errors.

Every test drives the real ``anthropic`` SDK through an ``httpx2`` mock transport;
no network request is made and no real credential is used.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest

from autoresearch.agents import _transport
from autoresearch.anthropic_provider import AnthropicProvider
from autoresearch.contracts import AgentRequest, ProviderConfig
from autoresearch.provider_presets import find, load_catalog, to_entry
from autoresearch.providers import CompatibleProvider, ProviderError, create_provider

KEY_ENV = "TEST_ANTHROPIC_KEY"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, "test-only-credential")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    monkeypatch.setattr("autoresearch.anthropic_provider.time.sleep", lambda _: None)


@pytest.fixture
def request_data() -> AgentRequest:
    return AgentRequest(
        run_id="test",
        stage="novelty",
        role="critic",
        system="Respond with one JSON object.",
        prompt="Check",
        temperature=0.3,
    )


def preset_config(model: str, **update: Any) -> ProviderConfig:
    provider, entry = find(f"anthropic:{model}", load_catalog())
    config = to_entry(provider, entry, tier="paid").provider
    return config.model_copy(update={"api_key_env": KEY_ENV, **update})


def message(
    text: str = '{"summary":"ok"}',
    *,
    stop: str = "end_turn",
    usage: dict[str, int] | None = None,
    thinking: bool = True,
    stop_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if thinking:
        content.append({"type": "thinking", "thinking": "", "signature": "sig"})
    content.append({"type": "text", "text": text})
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "stop_details": stop_details,
        "usage": usage
        or {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
    ).encode()


def stream_events(text: str = '{"summary":"ok"}', *, cut: bool = False) -> list[dict[str, Any]]:
    start = message(text="", usage={"input_tokens": 10, "output_tokens": 1})
    start["content"] = []
    start["stop_reason"] = None
    events: list[dict[str, Any]] = [
        {"type": "message_start", "message": start},
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "s"},
        },
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": text[:5]},
        },
    ]
    if cut:
        return events
    events += [
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": text[5:]},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 100,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
        {"type": "message_stop"},
    ]
    return events


class Recorder:
    def __init__(self, *responses: httpx2.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.responses.pop(0)

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self))


def run(config: ProviderConfig, request: AgentRequest, recorder: Recorder) -> Any:
    provider = AnthropicProvider(config, http_client=recorder.client())
    return provider.complete(request)


def ok(body: dict[str, Any] | None = None, **headers: str) -> httpx2.Response:
    return httpx2.Response(200, json=body or message(), headers={"request-id": "req_1", **headers})


def error(
    status: int, kind: str, headers: dict[str, str] | None = None, **extra: Any
) -> httpx2.Response:
    body = {"type": "error", "error": {"type": kind, "message": "synthetic", **extra}}
    return httpx2.Response(status, json=body, headers={"request-id": "req_err", **(headers or {})})


# ---------------------------------------------------------------- request shape


def test_opus_request_shape_has_no_sampling_effort_cache_and_system(
    request_data: AgentRequest,
) -> None:
    recorder = Recorder(ok())
    result = run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    sent = recorder.requests[0]
    body = recorder.body()
    assert str(sent.url) == "https://api.anthropic.com/v1/messages"
    assert sent.headers["x-api-key"] == "test-only-credential"
    assert "anthropic-version" in sent.headers
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 12000
    assert body["system"] == [
        {
            "type": "text",
            "text": "Respond with one JSON object.",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Check"}]}]
    assert body["output_config"] == {"effort": "medium"}
    for forbidden in ("temperature", "top_p", "top_k", "thinking", "tools", "tool_choice"):
        assert forbidden not in body
    # No assistant prefill.
    assert all(item["role"] == "user" for item in body["messages"])
    assert result.data == {"summary": "ok"}
    assert result.provider == "anthropic"


@pytest.mark.parametrize(
    ("model", "effort", "temperature"),
    [
        ("claude-opus-5-5", "medium", False),
        ("claude-sonnet-5-5", "high", False),
        ("claude-fable-5-1", "high", False),
        ("claude-haiku-5-5", "medium", False),
        ("claude-haiku-4-5", None, True),
    ],
)
def test_per_model_effort_and_sampling_flags(
    request_data: AgentRequest, model: str, effort: str | None, temperature: bool
) -> None:
    recorder = Recorder(ok())
    run(preset_config(model, streaming=False), request_data, recorder)
    body = recorder.body()
    assert body.get("output_config") == ({"effort": effort} if effort else None)
    assert ("temperature" in body) is temperature
    if temperature:
        assert body["temperature"] == 0.3
    assert "thinking" not in body


@pytest.mark.parametrize(
    ("metis", "anthropic"), [("minimal", "low"), ("xhigh", "xhigh"), ("max", "max")]
)
def test_reasoning_effort_maps_to_anthropic_levels(
    request_data: AgentRequest, metis: str, anthropic: str
) -> None:
    recorder = Recorder(ok())
    run(
        preset_config("claude-opus-5-5", streaming=False, reasoning_effort=metis),
        request_data,
        recorder,
    )
    assert recorder.body()["output_config"] == {"effort": anthropic}


def test_unknown_effort_is_rejected_before_any_request() -> None:
    with pytest.raises(ProviderError, match="Unsupported reasoning effort"):
        AnthropicProvider(preset_config("claude-opus-5-5", reasoning_effort="extreme"))


def test_split_context_marks_stable_reference_block_for_caching() -> None:
    context = {
        "project": {"id": "p"},
        "state": {"id": "s", "title": "t", "evidence": [{"i": n} for n in range(10)], "stage": "x"},
        "task": "y",
    }
    request = AgentRequest(
        run_id="r", stage="s", role="r", system="S", prompt=json.dumps(context), split_context=True
    )
    recorder = Recorder(ok())
    run(preset_config("claude-opus-5-5", streaming=False), request, recorder)
    content = recorder.body()["messages"][0]["content"]
    assert len(content) == 4  # references, two evidence chunks, current state
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in block for block in content[1:])
    assert json.loads(content[0]["text"])["project"] == {"id": "p"}


# ---------------------------------------------------------------- streaming and response


def test_streaming_feeds_progress_and_ignores_thinking(request_data: AgentRequest) -> None:
    recorder = Recorder(
        httpx2.Response(
            200,
            content=sse(stream_events()),
            headers={"content-type": "text/event-stream", "request-id": "req_s"},
        )
    )
    provider = AnthropicProvider(preset_config("claude-opus-5-5"), http_client=recorder.client())
    updates: list[dict[str, Any]] = []
    provider.progress = updates.append
    result = provider.complete(request_data)
    assert recorder.body()["stream"] is True
    assert result.data == {"summary": "ok"}
    statuses = [update["status"] for update in updates]
    assert statuses[0] == "waiting"
    assert "reasoning" in statuses and "receiving" in statuses
    assert updates[-1]["status"] == "received"
    assert updates[-1]["output"] == '{"summary":"ok"}'
    assert updates[-1]["response_id"] == "msg_01"
    assert result.usage.input_tokens == 1000
    assert result.usage.output_tokens == 100


def test_interrupted_stream_is_not_accepted_or_retried(request_data: AgentRequest) -> None:
    recorder = Recorder(
        httpx2.Response(
            200,
            content=sse(stream_events(cut=True)),
            headers={"content-type": "text/event-stream"},
        )
    )
    provider = AnthropicProvider(preset_config("claude-opus-5-5"), http_client=recorder.client())
    updates: list[dict[str, Any]] = []
    provider.progress = updates.append
    with pytest.raises(ProviderError, match="interrupted") as caught:
        provider.complete(request_data)
    assert len(recorder.requests) == 1
    assert not caught.value.recoverable
    assert caught.value.usage.estimated and caught.value.usage.cost_usd > 0
    assert updates[-1]["status"] == "interrupted"
    assert updates[-1]["output"] == '{"sum'


def test_text_blocks_are_joined_and_thinking_is_ignored(request_data: AgentRequest) -> None:
    body = message('```json\n{"summary": "fenced"}\n```')
    body["content"].insert(
        1, {"type": "thinking", "thinking": '{"summary":"wrong"}', "signature": "s"}
    )
    recorder = Recorder(ok(body))
    result = run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert result.data == {"summary": "fenced"}


def test_refusal_is_non_recoverable_and_records_category(request_data: AgentRequest) -> None:
    body = message(
        "",
        stop="refusal",
        stop_details={"type": "refusal", "category": "cyber", "explanation": "x"},
    )
    recorder = Recorder(ok(body))
    with pytest.raises(ProviderError, match="refusal, category cyber") as caught:
        run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert not caught.value.recoverable
    assert caught.value.details["refusal_category"] == "cyber"
    assert caught.value.usage.input_tokens == 1000  # billed usage is still settled
    assert len(recorder.requests) == 1


def test_max_tokens_stop_is_truncation(request_data: AgentRequest) -> None:
    recorder = Recorder(ok(message('{"summary":"ok"}', stop="max_tokens")))
    with pytest.raises(ProviderError, match="invalid or truncated") as caught:
        run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert not caught.value.recoverable
    assert caught.value.usage.output_tokens == 100


def test_non_object_json_is_rejected(request_data: AgentRequest) -> None:
    recorder = Recorder(ok(message("[1, 2]")))
    with pytest.raises(ProviderError, match="invalid or truncated"):
        run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)


# ---------------------------------------------------------------- accounting


def test_usage_prices_cache_reads_and_writes(request_data: AgentRequest) -> None:
    usage = {
        "input_tokens": 1000,
        "output_tokens": 500,
        "cache_creation_input_tokens": 2000,
        "cache_read_input_tokens": 10000,
    }
    recorder = Recorder(ok(message(usage=usage)))
    result = run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert result.usage.input_tokens == 13000
    assert result.usage.cached_input_tokens == 10000
    # Opus 5.5: $4 input, $20 output, $0.20 cache reads, writes at 1.25 x $4.
    expected = (1000 * 4 + 2000 * 4 * 1.25 + 10000 * 0.20 + 500 * 20) / 1e6
    assert result.usage.cost_usd == pytest.approx(expected)
    assert not result.usage.estimated


def test_haiku_5_5_long_prompt_price(request_data: AgentRequest) -> None:
    usage = {"input_tokens": 150_000, "output_tokens": 1000}
    recorder = Recorder(ok(message(usage=usage)))
    result = run(preset_config("claude-haiku-5-5", streaming=False), request_data, recorder)
    assert result.usage.cost_usd == pytest.approx((150_000 * 0.50 + 1000 * 2.50) / 1e6)


# ---------------------------------------------------------------- errors


def test_sdk_retries_disabled_and_metis_retries_bounded(request_data: AgentRequest) -> None:
    recorder = Recorder(error(500, "api_error"), error(500, "api_error"), ok())
    result = run(
        preset_config("claude-opus-5-5", streaming=False, retries=2), request_data, recorder
    )
    assert len(recorder.requests) == 3  # one per Metis attempt; the SDK added none
    assert result.usage.estimated  # failed attempts settle the conservative estimate
    assert result.usage.input_tokens > 1000


def test_persistent_500_is_recoverable_but_not_rate_limited(request_data: AgentRequest) -> None:
    recorder = Recorder(*(error(500, "api_error") for _ in range(2)))
    with pytest.raises(ProviderError, match="HTTP 500") as caught:
        run(preset_config("claude-opus-5-5", streaming=False, retries=1), request_data, recorder)
    assert caught.value.recoverable and not caught.value.rate_limited
    assert "req_err" in str(caught.value)
    assert caught.value.details["request_id"] == "req_err"


def test_529_overload_is_quota_wait_eligible(request_data: AgentRequest) -> None:
    recorder = Recorder(*(error(529, "overloaded_error", {"retry-after": "7"}) for _ in range(2)))
    with pytest.raises(ProviderError, match="529 overloaded_error") as caught:
        run(preset_config("claude-opus-5-5", streaming=False, retries=1), request_data, recorder)
    assert caught.value.recoverable and caught.value.rate_limited
    assert caught.value.retry_after_seconds == 7
    assert not caught.value.quota_exhausted_until


def test_short_window_429_retries_then_reports_rate_limit(request_data: AgentRequest) -> None:
    reset = (datetime.now(UTC) + timedelta(seconds=20)).isoformat()
    headers = {
        "retry-after": "20",
        "anthropic-ratelimit-requests-remaining": "0",
        "anthropic-ratelimit-requests-reset": reset,
    }
    recorder = Recorder(*(error(429, "rate_limit_error", headers) for _ in range(3)))
    with pytest.raises(ProviderError) as caught:
        run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert len(recorder.requests) == 3
    assert caught.value.rate_limited and caught.value.recoverable
    assert not caught.value.quota_exhausted_until


def test_long_window_429_uses_anthropic_reset_header(request_data: AgentRequest) -> None:
    reset = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    headers = {
        "anthropic-ratelimit-output-tokens-remaining": "0",
        "anthropic-ratelimit-output-tokens-limit": "80000",
        "anthropic-ratelimit-output-tokens-reset": reset,
    }
    recorder = Recorder(error(429, "rate_limit_error", headers))
    with pytest.raises(ProviderError, match="quota exhausted") as caught:
        run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert len(recorder.requests) == 1  # no in-request retries for a long window
    error_ = caught.value
    assert error_.rate_limited and error_.recoverable
    until = datetime.fromisoformat(error_.quota_exhausted_until)
    assert timedelta(hours=2, minutes=59) < until - datetime.now(UTC) <= timedelta(hours=3)
    assert error_.quota["quota_id"] == "anthropic-ratelimit-output-tokens"
    assert error_.quota["quota_value"] == "80000"
    assert error_.quota["window"] == "long"


def test_spend_cap_429_never_waits(request_data: AgentRequest) -> None:
    recorder = Recorder(
        error(429, "rate_limit_error", details={"error_code": "enforced_spend_limit_reached"})
    )
    with pytest.raises(ProviderError, match="spend cap") as caught:
        run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert len(recorder.requests) == 1
    assert caught.value.recoverable and not caught.value.rate_limited


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, "invalid_request_error"),
        (401, "authentication_error"),
        (403, "permission_error"),
        (404, "not_found_error"),
    ],
)
def test_client_errors_are_not_recoverable(
    request_data: AgentRequest, status: int, kind: str
) -> None:
    recorder = Recorder(error(status, kind))
    with pytest.raises(ProviderError, match=f"HTTP {status} {kind}") as caught:
        run(preset_config("claude-opus-5-5", streaming=False), request_data, recorder)
    assert len(recorder.requests) == 1
    assert not caught.value.recoverable and not caught.value.rate_limited
    assert "test-only-credential" not in str(caught.value)


def test_connection_failure_is_recoverable_and_charged(request_data: AgentRequest) -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("synthetic")

    config = preset_config("claude-opus-5-5", streaming=False, retries=1)
    provider = AnthropicProvider(
        config, http_client=httpx2.Client(transport=httpx2.MockTransport(fail))
    )
    with pytest.raises(ProviderError, match="transport failed") as caught:
        provider.complete(request_data)
    assert caught.value.recoverable
    assert caught.value.usage.estimated and caught.value.usage.cost_usd > 0


def test_missing_key_never_uses_other_anthropic_credentials(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.delenv(KEY_ENV)
    with pytest.raises(ProviderError, match="credential is missing"):
        AnthropicProvider(preset_config("claude-opus-5-5")).complete(request_data)


# ---------------------------------------------------------------- factory and presets


def test_factory_selects_adapter() -> None:
    assert isinstance(create_provider(preset_config("claude-opus-5-5")), AnthropicProvider)
    assert isinstance(_transport(preset_config("claude-opus-5-5")), AnthropicProvider)
    assert isinstance(create_provider(ProviderConfig()), CompatibleProvider)
    with pytest.raises(ProviderError, match="HTTPS"):
        create_provider(preset_config("claude-opus-5-5", base_url="http://api.anthropic.com"))


def test_default_client_disables_sdk_retries_proxies_and_redirects() -> None:
    provider = AnthropicProvider(preset_config("claude-opus-5-5"))
    client = provider._client("test-only-credential")
    try:
        assert client.max_retries == 0
        assert str(client.base_url).rstrip("/") == "https://api.anthropic.com"
        assert client._client.trust_env is False
        assert client._client.follow_redirects is False
    finally:
        client.close()
