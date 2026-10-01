"""Offline SSE fixtures exercise the real compatible HTTP transport."""

import json

import httpx
import pytest

from autoresearch.contracts import AgentRequest, ProviderConfig
from autoresearch.providers import CompatibleProvider, ProviderError


def event(value):
    return ("data: " + (value if isinstance(value, str) else json.dumps(value)) + "\n\n").encode()


def test_stream_keeps_reasoning_progress_and_final_usage(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "synthetic-key")
    progress = []
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(
                [
                    b": heartbeat\n\n",
                    event(
                        {
                            "id": "fixture-id",
                            "choices": [
                                {"index": 0, "delta": {"reasoning_content": "private thinking"}}
                            ],
                        }
                    ),
                    event({"choices": [{"index": 0, "delta": {"content": '{"summary":'}}]}),
                    event(
                        {
                            "choices": [
                                {"index": 0, "delta": {"content": '"ok"}'}, "finish_reason": "stop"}
                            ]
                        }
                    ),
                    event(
                        {"choices": [], "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}
                    ),
                    event("[DONE]"),
                ]
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = CompatibleProvider(ProviderConfig(), client=client)
        provider.progress = progress.append
        result = provider.complete(
            AgentRequest(
                run_id="test",
                stage="limitations",
                role="limitations",
                system="JSON",
                prompt="Synthetic",
            )
        )
    assert result.data == {"summary": "ok"}
    assert json.loads(seen[0].content)["stream"] is True
    assert seen[0].extensions["timeout"]["read"] == 3600
    assert not result.usage.estimated
    assert result.usage.cost_usd == pytest.approx(0.0026)
    assert progress[-1]["status"] == "received"
    assert progress[-1]["response_id"] == "fixture-id"
    assert "".join(p.get("output", "") for p in progress) == '{"summary":"ok"}'
    assert "private thinking" not in json.dumps(progress)


@pytest.mark.parametrize("ending", ["eof", "timeout", "length", "malformed", "error"])
def test_incomplete_stream_preserved_without_retry_or_acceptance(monkeypatch, ending):
    monkeypatch.setenv("XAI_API_KEY", "synthetic-key")
    progress = []
    seen = []

    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield event(
                {"id": "partial-id", "choices": [{"delta": {"content": '{"summary":"partial"}'}}]}
            )
            if ending == "timeout":
                raise httpx.ReadTimeout("private transport text")
            if ending == "length":
                yield event({"choices": [{"delta": {}, "finish_reason": "length"}]})
                yield event("[DONE]")
            if ending == "malformed":
                yield event("not-json")
            if ending == "error":
                yield event({"error": {"message": "private upstream text"}})

    def handle(request):
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Broken())

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = CompatibleProvider(ProviderConfig(retries=2), client=client)
        provider.progress = progress.append
        with pytest.raises(ProviderError, match="stream interrupted") as error:
            provider.complete(
                AgentRequest(
                    run_id="test",
                    stage="limitations",
                    role="limitations",
                    system="JSON",
                    prompt="Synthetic",
                )
            )
    assert len(seen) == 1
    assert not error.value.recoverable
    assert error.value.usage.estimated
    assert error.value.usage.cost_usd > 0
    assert progress[-1]["status"] == "interrupted"
    assert "".join(p.get("output", "") for p in progress) == '{"summary":"partial"}'
    assert "private" not in str(error.value)


def test_repeated_usage_is_not_double_counted_and_streaming_can_be_disabled(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "synthetic-key")
    usage = {"prompt_tokens": 1000, "completion_tokens": 100}

    def handle(request):
        assert json.loads(request.content)["stream"] is False
        assert "stream_options" not in json.loads(request.content)
        assert request.extensions["timeout"]["read"] == 27
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(
                [
                    event(
                        {
                            "choices": [
                                {"delta": {"content": '{"summary":"ok"}'}, "finish_reason": "stop"}
                            ],
                            "usage": usage,
                        }
                    ),
                    event({"choices": [], "usage": usage}),
                    event("[DONE]"),
                ]
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = CompatibleProvider(
            ProviderConfig(streaming=False, timeout_seconds=27), client=client
        ).complete(
            AgentRequest(
                run_id="test",
                stage="limitations",
                role="limitations",
                system="JSON",
                prompt="Synthetic",
            )
        )
    assert result.usage.input_tokens == 1000
    assert result.usage.cost_usd == pytest.approx(0.0026)


def test_runner_links_stream_events_and_honors_metadata_privacy(tmp_path, monkeypatch):
    from autoresearch.agents import AgentRunner
    from autoresearch.config import ResearchConfig
    from autoresearch.contracts import AgentOutput, RunState
    from autoresearch.process_view import process_view
    from autoresearch.store import Store, now

    monkeypatch.setenv("XAI_API_KEY", "synthetic-key")
    output = AgentOutput(
        summary="Synthetic accepted transport", confidence=1, limitations=["Fixture only"]
    ).model_dump_json()

    def handle(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(
                [
                    event(
                        {
                            "id": "journal-id",
                            "choices": [{"delta": {"content": output}, "finish_reason": "stop"}],
                        }
                    ),
                    event({"usage": {"prompt_tokens": 10, "completion_tokens": 10}}),
                    event("[DONE]"),
                ]
            ),
        )

    monkeypatch.setattr(
        "autoresearch.agents.CompatibleProvider",
        lambda cfg: CompatibleProvider(
            cfg, client=httpx.Client(transport=httpx.MockTransport(handle))
        ),
    )
    for privacy in ["redacted", "metadata"]:
        cfg = ResearchConfig()
        cfg.privacy.traces = privacy
        store = Store(tmp_path / privacy)
        state = RunState(
            id="0123456789ab",
            title="Synthetic",
            objective="Fixture",
            created_at=now(),
            updated_at=now(),
        )
        store.create(state, cfg)
        AgentRunner(store, cfg)._one(state, "limitations", {}, 0)
        events = store.events(state.id)
        start = next(e["payload"] for e in events if e["kind"] == "agent_started")
        chunks = [e["payload"] for e in events if e["kind"] == "agent_progress"]
        assert chunks and all(e["call_id"] == start["call_id"] for e in chunks)
        if privacy == "metadata":
            assert all("output" not in e for e in chunks)
        else:
            assert "".join(e.get("output", "") for e in chunks) == output
        assert store.usage(state.id)["calls"] == 1
        assert store.usage(state.id)["reserved_usd"] == 0
        cfg.privacy.cache = False
        AgentRunner(store, cfg)._one(state, "limitations", {}, 0)
        projection = process_view(store, state.id)
        assert not any(row["label"] == "Unlinked agent start" for row in projection["rows"])


def test_interim_usage_cannot_settle_interrupted_generation_as_exact(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "synthetic-key")
    content = event(
        {
            "choices": [{"delta": {"content": "{"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=content
            )
        )
    ) as client:
        cfg = ProviderConfig(retries=0)
        request = AgentRequest(
            run_id="test",
            stage="limitations",
            role="limitations",
            system="JSON",
            prompt="Synthetic",
        )
        provider = CompatibleProvider(cfg, client=client)
        with pytest.raises(ProviderError) as error:
            provider.complete(request)
        assert error.value.usage.estimated
        assert error.value.usage.cost_usd >= provider._estimate(request).cost_usd


def test_progress_does_not_leak_secret_across_chunk_boundaries(monkeypatch):
    from autoresearch.privacy import redact

    monkeypatch.setenv("XAI_API_KEY", "synthetic-key")
    clock = iter(range(100, 10000, 10))
    monkeypatch.setattr("autoresearch.providers.time.monotonic", lambda: next(clock))
    recorded = []
    content = b"".join(
        [
            event({"choices": [{"delta": {"content": '{"summary":"private-person-'}}]}),
            event({"choices": [{"delta": {"content": 'name"}'}, "finish_reason": "stop"}]}),
            event("[DONE]"),
        ]
    )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=content
            )
        )
    ) as client:
        provider = CompatibleProvider(ProviderConfig(), client=client)
        provider.progress = lambda p: recorded.append(redact(p, ["private-person-name"]))
        provider.complete(
            AgentRequest(
                run_id="test",
                stage="limitations",
                role="limitations",
                system="JSON",
                prompt="Synthetic",
            )
        )
    assert all("output" not in p for p in recorded[:-1])
    assert "private-person-name" not in "".join(p.get("output", "") for p in recorded)
    assert "[REDACTED]" in recorded[-1]["output"]
