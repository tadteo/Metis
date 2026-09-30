"""Google routing retains expensive decisions and existing operator choices."""

import json

import httpx
import pytest

from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentRequest, ProviderConfig
from autoresearch.model_profiles import apply_model_profile
from autoresearch.providers import CompatibleProvider
from autoresearch.routing import resolve_route
from autoresearch.settings import load_settings
from autoresearch.store import Store


def test_profile_routes_google_transport_and_preserves_scientific_work(monkeypatch):
    original = ResearchConfig()
    config = apply_model_profile(original, "google-flash")
    assert original == ResearchConfig()
    assert config.pipeline == original.pipeline
    assert not config.laya.enabled
    for role in (
        "baseline",
        "full",
        "ablation",
        "ablation_plan",
        "meta_review",
        "integrity",
        "select",
    ):
        assert resolve_route(config, role).provider == original.provider
    assert resolve_route(config, "coding_step", original_role="full").provider == original.provider
    assert resolve_route(config, "review_summary", frontier=True).provider == original.provider
    route = resolve_route(config, "review_summary")
    monkeypatch.setattr(
        "autoresearch.providers.resolve",
        lambda name: ("synthetic-google-token", "session")
        if name == "GEMINI_API_KEY"
        else pytest.fail("Wrong credential"),
    )

    def response(request):
        assert (
            str(request.url)
            == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        )
        assert request.headers["Authorization"] == "Bearer synthetic-google-token"
        payload = json.loads(request.content)
        assert payload["model"] == "gemini-3.8-flash"
        assert payload["reasoning_effort"] == "medium"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"summary":"synthetic"}'}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = CompatibleProvider(route.provider, client=client).complete(
            AgentRequest(
                run_id="fixture",
                stage="review",
                role="review_summary",
                system="Return JSON",
                prompt="Fixture",
            )
        )
    assert result.provider == "google"
    assert result.usage.cost_usd == pytest.approx(0.0015)
    assert apply_model_profile(config, "google-flash") == config


def test_profile_preserves_custom_routes_and_unrelated_config():
    base = ResearchConfig()
    custom = ProviderConfig(model="custom-fixture")
    base.provider = custom
    base.cheap_provider = custom
    base.frontier_provider = custom
    base.role_providers["limitations"] = custom
    base.role_panels["review_summary"] = [custom]
    base.role_commands["review_historian"] = ["fixture-adapter"]
    base.role_command_max_cost_usd["review_historian"] = 1
    base.paper_orchestra.writer_model_name = "explicit-writer"
    base.laya.enabled = True
    base.project.specification = "Preserve immutable evaluation"
    updated = apply_model_profile(base, "google-flash")
    for field in (
        "provider",
        "cheap_provider",
        "frontier_provider",
        "role_panels",
        "role_commands",
        "paper_orchestra",
        "laya",
        "project",
        "budget",
        "privacy",
    ):
        assert getattr(updated, field) == getattr(base, field)
    assert updated.role_providers["limitations"] == custom
    assert "review_summary" not in updated.role_providers
    assert "review_historian" not in updated.role_providers


def test_cli_profile_saves_defaults_without_creating_or_running_research(tmp_path):
    assert main(["--state-dir", str(tmp_path), "settings", "profile", "google-flash"]) == 0
    store = Store(tmp_path)
    config, revision = load_settings(store)
    assert revision > 0
    assert config.cheap_provider.name == "google"
    assert store.list_runs() == []
    assert main(["--state-dir", str(tmp_path), "settings", "profile", "unknown"]) == 1
    assert load_settings(store) == (config, revision)
