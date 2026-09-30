import httpx
import pytest

from autoresearch.config import LayaConfig
from autoresearch.laya import LayaClient


def test_laya_uses_real_typed_protocol() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/systemone"
        assert b'"questions"' in request.content
        assert b'"max_len":8192' in request.content
        return httpx.Response(
            200,
            json={
                "answers": {"triage": {"noul": 0.9}},
                "usage": {"input_tokens": 30, "output_tokens": 0},
            },
        )

    client = LayaClient(LayaConfig(), httpx.Client(transport=httpx.MockTransport(respond)))
    result, usage = client.decide(
        {"task": "inspect"}, {"triage": {"type": "noul", "instructions": "Needs reasoning?"}}
    )
    assert result["answers"]["triage"]["noul"] == 0.9
    assert usage.input_tokens == 30 and usage.output_tokens == 0
    with pytest.raises(ValueError, match="context"):
        client.decide({"task": "x" * 10000}, {})


@pytest.mark.parametrize(
    "answer",
    [None, [], {"noul": True}, {"noul": -0.1}, {"noul": 1.1}, {"noul": "0.9"}, {"choice": "yes"}],
)
def test_laya_rejects_malformed_typed_answers_with_charged_failure(answer):
    from autoresearch.providers import ProviderError

    client = LayaClient(
        LayaConfig(cost_per_call_usd=0.01),
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"answers": {"triage": answer}})
            )
        ),
    )
    with pytest.raises(ProviderError) as error:
        client.decide({}, {"triage": {"type": "noul", "instructions": "Needs reasoning?"}})
    assert error.value.usage.cost_usd == 0.01
    assert error.value.usage.estimated is True


@pytest.mark.parametrize(
    "usage",
    [
        None,
        [],
        {"input_tokens": True, "output_tokens": 0},
        {"input_tokens": -1, "output_tokens": 0},
        {"input_tokens": 12},
        {"unexpected": "shape"},
    ],
)
def test_invalid_usage_cannot_leak_an_unhandled_exception(usage):
    from autoresearch.providers import ProviderError

    client = LayaClient(
        LayaConfig(cost_per_call_usd=0.01),
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"answers": {"triage": {"noul": 0.8}}, "usage": usage}
                )
            )
        ),
    )
    with pytest.raises(ProviderError) as error:
        client.decide({}, {"triage": {"type": "noul", "instructions": "Needs reasoning?"}})
    assert error.value.usage.cost_usd == 0.01


@pytest.mark.parametrize("cache", [True, False])
def test_triage_respects_run_privacy_and_preserves_real_call_denominator(
    tmp_path, monkeypatch, cache
):
    import json

    from autoresearch.config import ResearchConfig
    from autoresearch.contracts import RunState
    from autoresearch.laya import triage
    from autoresearch.store import Store

    config = ResearchConfig()
    config.privacy.cache = cache
    config.privacy.redact_patterns = ["private-mechanism"]
    config.laya.cost_per_call_usd = 0.01
    state = RunState(id="aabbccddeeff", title="Fixture", objective="Advice")
    store = Store(tmp_path / "private")
    store.create(state, config)
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"needs_deeper_analysis": {"noul": 0.9}}})

    client = LayaClient(config.laya, httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr("autoresearch.laya.LayaClient", lambda cfg: client)
    for _ in range(2):
        result = triage(
            store, state.id, "filter_ideas", config.laya, {"feedback": "private-mechanism"}
        )
        assert result["available"] and result["advisory_only"]
    assert len(sent) == (1 if cache else 2)
    assert "private-mechanism" not in str(sent)
    assert store.usage(state.id)["cost_usd"] == pytest.approx(0.01 * len(sent))
    assert store.usage(state.id)["model_calls_attempted"] == len(sent)


def test_failed_laya_advice_does_not_replace_independent_reasoning(tmp_path, monkeypatch):
    import json

    from autoresearch.agents import AgentRunner
    from autoresearch.config import ResearchConfig
    from autoresearch.contracts import AgentOutput, AgentResponse, RunState
    from autoresearch.store import Store

    config = ResearchConfig()
    config.laya.enabled = True
    config.laya.cost_per_call_usd = 0.01
    state = RunState(id="001122334455", title="Fixture", objective="Keep critic")
    store = Store(tmp_path / "private")
    store.create(state, config)
    client = LayaClient(
        config.laya,
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable"))
        ),
    )
    monkeypatch.setattr("autoresearch.laya.LayaClient", lambda cfg: client)
    calls = []

    class Reasoning:
        def complete(self, request):
            calls.append(json.loads(request.prompt))
            return AgentResponse(
                data=AgentOutput(
                    summary="Measured objection", decision="reject", confidence=1
                ).model_dump(),
                provider="fixture",
                model="fixture",
            )

    result = AgentRunner(store, config, Reasoning()).run(state, "filter_ideas")
    assert result.decision == "reject"
    assert len(calls) == config.pipeline.critics
    assert all(call["laya_triage"]["available"] is False for call in calls)
    assert store.usage(state.id)["cost_usd"] == pytest.approx(0.01)
    assert any(e["kind"] == "model_escalation" for e in store.events(state.id))


@pytest.mark.parametrize(
    "kind, criteria, value",
    [
        ("noul", None, 0.0),
        ("noul", None, 1.0),
        ("choice", {"repair": "fix method", "reject": "discard method"}, "repair"),
        ("score", ["weak", "medium", "strong"], 1.75),
    ],
)
def test_public_typed_values_and_bearer_contract(kind, criteria, value, monkeypatch):
    import json

    monkeypatch.setenv("LAYA_TEST_TOKEN", "synthetic-local-fixture")
    question = {"type": kind, "instructions": "Evaluate evidence"}
    if criteria is not None:
        question["criteria"] = criteria

    def respond(request):
        assert request.headers["Authorization"] == "Bearer synthetic-local-fixture"
        assert json.loads(request.content)["questions"] == {"triage": question}
        return httpx.Response(200, json={"answers": {"triage": {kind: value}}})

    client = LayaClient(
        LayaConfig(api_key_env="LAYA_TEST_TOKEN"),
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    result, usage = client.decide({}, {"triage": question})
    assert result["answers"]["triage"][kind] == value
    assert usage.estimated


def test_nonfinite_and_oversized_numbers_are_charged_failures():
    from autoresearch.providers import ProviderError

    for value in ("NaN", "Infinity", "1" + "0" * 400):
        client = LayaClient(
            LayaConfig(cost_per_call_usd=0.01),
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda request, value=value: httpx.Response(
                        200, text='{"answers":{"triage":{"noul":' + value + "}}}"
                    )
                )
            ),
        )
        with pytest.raises(ProviderError):
            client.decide({}, {"triage": {"type": "noul"}})


def test_laya_uses_saved_session_credentials_and_preserves_auth_failure(monkeypatch):
    from autoresearch import credentials
    from autoresearch.providers import ProviderError

    monkeypatch.setattr(credentials, "_session", {"LAYA_FIXTURE_KEY": "synthetic-session-laya-key"})
    monkeypatch.setenv("LAYA_FIXTURE_KEY", "must-not-win-over-session")

    def response(request):
        assert request.headers["Authorization"] == "Bearer synthetic-session-laya-key"
        return httpx.Response(200, json={"answers": {"triage": {"noul": 0.7}}})

    config = LayaConfig(api_key_env="LAYA_FIXTURE_KEY")
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result, _ = LayaClient(config, client).decide(
            {}, {"triage": {"type": "noul", "instructions": "Fixture"}}
        )
    assert result["answers"]["triage"]["noul"] == 0.7

    def fail(_):
        raise credentials.CredentialAccessError("Host credential vault could not be read.")

    monkeypatch.setattr("autoresearch.laya.resolve", fail)
    with pytest.raises(ProviderError, match="vault"):
        LayaClient(config).decide({}, {"triage": {"type": "noul", "instructions": "Fixture"}})
