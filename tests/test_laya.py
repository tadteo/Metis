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
