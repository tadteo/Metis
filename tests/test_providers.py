from __future__ import annotations

import json

import httpx
import pytest

from autoresearch import credentials
from autoresearch.contracts import AgentRequest, ProviderConfig
from autoresearch.providers import CompatibleProvider, ProviderError


@pytest.fixture
def request_data() -> AgentRequest:
    return AgentRequest(
        run_id="test", stage="novelty", role="critic", system="Return JSON", prompt="Check"
    )


def reply(content: str = '{"summary":"ok"}', *, usage: bool = True) -> dict[str, object]:
    result: dict[str, object] = {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}]
    }
    if usage:
        result["usage"] = {"prompt_tokens": 1000, "completion_tokens": 100}
    return result


def test_compatible_transport_explicit_key_and_usage(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "test-only-credential")
    monkeypatch.setenv("XAI_API_KEY", "different-credential")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=reply())

    config = ProviderConfig(
        api_key_env="TEST_PROVIDER_KEY", input_per_million=2, output_per_million=6
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CompatibleProvider(config, client=client).complete(request_data)
    assert str(seen[0].url) == "https://api.x.ai/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer test-only-credential"
    payload = json.loads(seen[0].content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"
    assert result.data == {"summary": "ok"}
    assert result.usage.cost_usd == pytest.approx(0.0026)
    assert result.usage.input_tokens == 1000
    assert not result.usage.estimated


def test_missing_key_never_falls_back_to_other_credentials(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.delenv("MISSING_CUSTOM_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "must-not-be-used")
    with pytest.raises(ProviderError, match="MISSING_CUSTOM_KEY") as caught:
        CompatibleProvider(ProviderConfig(api_key_env="MISSING_CUSTOM_KEY")).complete(request_data)
    assert caught.value.usage.cost_usd == 0


def test_non_ascii_credentials_cannot_leak_via_header_encoding_errors(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "synthetic-private-\u2665")
    with pytest.raises(ProviderError, match="invalid characters") as caught:
        CompatibleProvider(ProviderConfig()).complete(request_data)
    assert "synthetic-private" not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "https://example.com/v1#fragment",
        "file:///private/key",
    ],
)
def test_insecure_or_ambiguous_provider_urls_rejected(url: str) -> None:
    with pytest.raises(ProviderError):
        CompatibleProvider(ProviderConfig(base_url=url))


def test_local_endpoint_without_credentials(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.delenv("LOCAL_TEST_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json=reply())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = CompatibleProvider(
            ProviderConfig(base_url="http://127.0.0.1:8080/v1", api_key_env="LOCAL_TEST_KEY"),
            client=client,
        )
        assert provider.complete(request_data).data["summary"] == "ok"


def test_provider_uses_in_app_session_key_without_environment(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    name = "METIS_TEST_PROVIDER_KEY"
    value = "synthetic-provider-key-123456"
    monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    credentials.save(name, value, "session")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {value}"
        return httpx.Response(200, json=reply())

    try:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            provider = CompatibleProvider(ProviderConfig(api_key_env=name), client=client)
            assert provider.complete(request_data).data["summary"] == "ok"
    finally:
        credentials.clear(name)


@pytest.mark.parametrize(
    "content", ["[]", "null", "not json", '{"x":NaN}', '{"x":1e999}', '{"x":1,"x":2}']
)
def test_invalid_model_json_retains_billable_usage(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest, content: str
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-credential")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=reply(content)))
    ) as client:
        with pytest.raises(ProviderError, match="JSON object") as caught:
            CompatibleProvider(ProviderConfig(), client=client).complete(request_data)
    assert caught.value.usage.output_tokens == 100


def test_retries_are_bounded_and_all_attempts_count(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-credential")
    monkeypatch.setattr("autoresearch.providers.time.sleep", lambda _: None)
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "sensitive upstream body"})
        return httpx.Response(200, json=reply())

    config = ProviderConfig(retries=2, max_output_tokens=256)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CompatibleProvider(config, client=client).complete(request_data)
    assert attempts == 3
    assert result.usage.estimated
    assert result.usage.output_tokens == 256 * 2 + 100
    assert result.usage.cost_usd > 0.0026


def test_http_errors_do_not_leak_response_body_or_key(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "do-not-leak-credential")
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": "do-not-leak-credential private prompt"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as caught:
            CompatibleProvider(ProviderConfig(), client=client).complete(request_data)
    assert str(caught.value) == "Provider request rejected (HTTP 401)"
    assert attempts == 1
    assert caught.value.usage.estimated


def test_redirect_does_not_send_key_to_another_host(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-credential")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(307, headers={"location": "https://attacker.example/v1"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(ProviderError, match="HTTP 307"):
            CompatibleProvider(ProviderConfig(), client=client).complete(request_data)
    assert seen == ["api.x.ai"]


def test_transport_failure_accounts_uncertain_billing(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-credential")
    monkeypatch.setattr("autoresearch.providers.time.sleep", lambda _: None)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("private exception", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="Provider transport failed") as caught:
            CompatibleProvider(
                ProviderConfig(retries=1, max_output_tokens=256), client=client
            ).complete(request_data)
    assert attempts == 2
    assert caught.value.usage.output_tokens == 512
    assert caught.value.usage.estimated


def test_long_context_rate_uses_actual_input_usage(
    monkeypatch: pytest.MonkeyPatch, request_data: AgentRequest
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-credential")
    config = ProviderConfig(
        long_context_threshold=500, long_input_per_million=4, long_output_per_million=12
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=reply()))
    ) as client:
        result = CompatibleProvider(config, client=client).complete(request_data)
    assert result.usage.cost_usd == pytest.approx(0.0052)


def test_xai_cache_affinity_and_usage(monkeypatch, request_data):
    monkeypatch.setenv("XAI_API_KEY", "fixture")
    seen = []

    def handler(request):
        seen.append(request)
        body = reply()
        body["usage"]["prompt_tokens_details"] = {"cached_tokens": 800}
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = CompatibleProvider(ProviderConfig(), client=client)
        first = provider.complete(request_data)
        request_data.prompt = "Changed feedback"
        request_data.cache_key = "different-local-response-key"
        provider.complete(request_data)
        request_data.run_id = "another-run"
        provider.complete(request_data)
    assert seen[0].headers.get("x-grok-conv-id")
    assert seen[0].headers["x-grok-conv-id"] == seen[1].headers["x-grok-conv-id"]
    assert seen[0].headers["x-grok-conv-id"] != seen[2].headers["x-grok-conv-id"]
    assert first.usage.cached_input_tokens == 800
    assert first.usage.input_tokens == 1000
    assert not first.usage.cached  # local response reuse is a different cache


@pytest.mark.parametrize("cached", [None, -1, True, "800", 1001, 0, 800])
def test_cache_receipts_distinguish_unknown_from_zero(request_data, cached):
    body = reply()
    body["usage"]["prompt_tokens_details"] = {"cached_tokens": cached}
    usage = CompatibleProvider(ProviderConfig())._reported_usage(
        body, CompatibleProvider(ProviderConfig())._estimate(request_data)
    )
    assert usage.cached_input_tokens == (
        cached if type(cached) is int and 0 <= cached <= 1000 else None
    )


def test_xai_affinity_not_sent_to_other_endpoints(monkeypatch, request_data):
    monkeypatch.setenv("XAI_API_KEY", "fixture")

    def handle(request):
        assert "x-grok-conv-id" not in request.headers
        return httpx.Response(200, json=reply())

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        CompatibleProvider(
            ProviderConfig(base_url="https://example.org/v1"), client=client
        ).complete(request_data)


def test_retry_cache_counts_remain_unknown_when_attempt_usage_missing(monkeypatch, request_data):
    monkeypatch.setenv("XAI_API_KEY", "fixture")
    monkeypatch.setattr("autoresearch.providers.time.sleep", lambda _: None)
    seen = []

    def handle(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(503, json={})
        body = reply()
        body["usage"]["prompt_tokens_details"] = {"cached_tokens": 800}
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = CompatibleProvider(ProviderConfig(retries=1), client=client).complete(request_data)
    assert len(seen) == 2
    assert seen[0].headers["x-grok-conv-id"] == seen[1].headers["x-grok-conv-id"]
    assert result.usage.estimated
    assert result.usage.cached_input_tokens is None
