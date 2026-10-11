"""Paid provider presets (OpenAI, Anthropic, Gemini Pro, DeepSeek) and request-shape flags."""

from __future__ import annotations

import json

import httpx
import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentRequest, ProviderConfig
from autoresearch.model_inventory import ModelInventory
from autoresearch.model_selection import model_facts
from autoresearch.paper_orchestra import preflight_writer, resolve_writer_config
from autoresearch.provider_presets import find, load_catalog, to_entry
from autoresearch.providers import CompatibleProvider

REQUEST = AgentRequest(run_id="r", stage="s", role="critic", system="Return JSON", prompt="Hi")


def entry(reference: str, tier: str = "paid"):  # type: ignore[no-untyped-def]
    provider, model = find(reference, load_catalog())
    return to_entry(provider, model, tier=tier)  # type: ignore[arg-type]


def send(config: ProviderConfig, usage: dict[str, object]) -> tuple[dict[str, object], object]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": usage,
        }
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CompatibleProvider(config, client=client).complete(REQUEST)
    return json.loads(seen[0].content), result


@pytest.mark.parametrize(
    ("reference", "tier"),
    [
        ("openai:gpt-6-astra", "frontier"),
        ("openai:gpt-6.1-sol", "strong"),
        ("openai:gpt-6-luna", "light"),
        ("anthropic:claude-fable-5-1", "frontier"),
        ("anthropic:claude-opus-5-5", "frontier"),
        ("anthropic:claude-sonnet-5-5", "strong"),
        ("anthropic:claude-haiku-5-5", "light"),
        ("anthropic:claude-haiku-4-5", "light"),
        ("google:gemini-3.1-pro-preview", "frontier"),
        ("deepseek:deepseek-flash", "standard"),
        ("deepseek:deepseek-v4-pro", "standard"),
    ],
)
def test_paid_presets_are_sourced_and_tiered(reference: str, tier: str) -> None:
    provider, model = find(reference, load_catalog())
    assert model.capability is not None and model.capability.tier == tier
    assert model.capability.basis == "provider-published"
    for field in ("context_window", "max_output_tokens", "input_per_million", "output_per_million"):
        value = getattr(model, field)
        assert value is not None and value.source_url.startswith("https://")
        assert value.checked_at.isoformat() == "2026-10-08"
    assert model.cached_input_per_million is not None
    assert provider.data_use is not None
    facts = model_facts(entry(reference))
    assert facts["plan"] == "paid" and facts["tier"] == tier


def test_anthropic_preset_uses_native_adapter_and_published_prices() -> None:
    config = entry("anthropic:claude-opus-5-5").provider
    assert config.adapter == "anthropic"
    assert config.base_url == "https://api.anthropic.com"
    assert config.api_key_env == "ANTHROPIC_API_KEY"
    assert (config.input_per_million, config.output_per_million) == (4.0, 20.0)
    assert config.cached_input_per_million == 0.20
    assert config.send_temperature is False and config.reasoning_effort == "medium"
    sonnet = entry("anthropic:claude-sonnet-5-5").provider
    assert sonnet.cached_input_per_million == 0.10  # pricing page: 5% of $2
    haiku = entry("anthropic:claude-haiku-5-5").provider
    assert (haiku.long_context_threshold, haiku.long_input_per_million) == (100000, 0.50)
    legacy = entry("anthropic:claude-haiku-4-5").provider
    assert legacy.send_temperature is True and legacy.reasoning_effort is None


def test_no_free_tier_for_paid_only_presets() -> None:
    for reference in ("anthropic:claude-opus-5-5", "google:gemini-3.1-pro-preview"):
        assert model_facts(entry(reference, "free"))["plan"] == "unavailable"


def test_openai_reasoning_request_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-credential")
    config = entry("openai:gpt-6-astra").provider.model_copy(update={"streaming": False})
    assert config.base_url == "https://api.openai.com/v1"
    body, result = send(
        config,
        {
            "prompt_tokens": 300_000,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 100_000},
        },
    )
    assert "temperature" not in body and "max_tokens" not in body
    assert body["max_completion_tokens"] == 12000
    assert body["response_format"] == {"type": "json_object"}
    # >272K input: 2x input and cache rates, 1.5x output for the full request.
    expected = (200_000 * 20 + 100_000 * 2.0 + 10 * 75) / 1e6
    assert result.usage.cost_usd == pytest.approx(expected)  # type: ignore[attr-defined]
    assert result.usage.cached_input_tokens == 100_000  # type: ignore[attr-defined]


def test_default_request_shape_and_cache_pricing_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-only-credential")
    config = ProviderConfig(streaming=False)
    body, result = send(
        config,
        {
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 800},
        },
    )
    assert body["temperature"] == 0.5 and body["max_tokens"] == 12000
    assert "max_completion_tokens" not in body
    # Without a configured cached rate, cache reads are charged at the full input rate.
    assert result.usage.cost_usd == pytest.approx((1000 * 2 + 100 * 6) / 1e6)  # type: ignore[attr-defined]


def test_deepseek_cache_hits_are_recorded_and_priced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-credential")
    config = entry("deepseek:deepseek-flash").provider.model_copy(update={"streaming": False})
    assert config.base_url == "https://api.deepseek.com"
    body, result = send(
        config, {"prompt_tokens": 1000, "completion_tokens": 100, "prompt_cache_hit_tokens": 600}
    )
    assert "temperature" not in body
    assert result.usage.cached_input_tokens == 600  # type: ignore[attr-defined]
    expected = (400 * 0.30 + 600 * 0.006 + 100 * 1.20) / 1e6
    assert result.usage.cost_usd == pytest.approx(expected)  # type: ignore[attr-defined]


def test_new_provider_fields_keep_existing_serialization() -> None:
    assert set(ProviderConfig().model_dump(mode="json")) == {
        "name", "base_url", "model", "api_key_env", "input_per_million", "output_per_million",
        "long_input_per_million", "long_output_per_million", "long_context_threshold",
        "max_output_tokens", "timeout_seconds", "streaming", "retries", "json_mode",
        "reasoning_effort",
    }  # fmt: skip
    flash = entry("google:gemini-3.8-flash", "free")
    stored = json.loads(ModelInventory(models=[flash]).model_dump_json())
    preset_model = stored["models"][0]["preset"]["model"]
    for absent in ("cached_input_per_million", "long_context_threshold", "request"):
        assert absent not in preset_model
    assert "adapter" not in stored["models"][0]["provider"]


def test_writer_preflight_rejects_anthropic_writing_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-credential")
    config = ResearchConfig(provider=entry("anthropic:claude-opus-5-5").provider)
    assert (
        resolve_writer_config(config)["compatible_models"]["metis-writer"]["adapter"] == "anthropic"
    )
    errors = preflight_writer(config)["errors"]
    assert any("manuscript writer cannot use Anthropic models" in error for error in errors)
    default = preflight_writer(ResearchConfig())["errors"]
    assert not any("Anthropic" in error for error in default)
