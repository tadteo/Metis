"""First-class Laya typed-decision transport; advisory triage, never invented prose.

Official API: https://github.com/NandhaKishorM/laya (POST /v1/systemone).
The released model is non-generative and cannot replace a scientific writing/coding role.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from .config import LayaConfig
from .contracts import Usage
from .privacy import redact
from .providers import ProviderError, strict_json
from .store import Store


class LayaClient:
    def __init__(self, config: LayaConfig, client: httpx.Client | None = None):
        self.config, self.client = config, client
        url = urlsplit(config.base_url)
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (
                url.scheme != "https"
                and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})
            )
        ):
            raise ValueError("Laya requires HTTPS or a loopback HTTP endpoint")

    def decide(
        self, state: dict[str, Any], questions: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        config = self.config
        encoded = json.dumps(state, allow_nan=False)
        for question in questions.values():
            if (
                not isinstance(question, dict)
                or not isinstance(question.get("type"), str)
                or question["type"] not in {"noul", "choice", "score"}
            ):
                raise ValueError("Unsupported Laya typed question")
            criteria = question.get("criteria")
            if question["type"] == "choice" and (
                not isinstance(criteria, (dict, list)) or not criteria
            ):
                raise ValueError("Laya choice requires nonempty criteria")
            if question["type"] == "score" and (not isinstance(criteria, list) or not criteria):
                raise ValueError("Laya score requires nonempty ordered criteria")
        if len(encoded) > config.max_input_chars:
            raise ValueError("Laya input exceeds declared context; escalate without truncating")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(config.api_key_env, "")
        if key:
            if not key.isascii() or any(c.isspace() for c in key):
                raise ValueError("Invalid Laya credential")
            headers["Authorization"] = f"Bearer {key}"
        client = self.client or httpx.Client(trust_env=False)
        started = time.monotonic()
        try:
            response = client.post(
                config.base_url.rstrip("/") + "/v1/systemone",
                headers=headers,
                json={
                    "state": state,
                    "questions": questions,
                    "model": config.model,
                    "max_len": config.max_len,
                },
                timeout=config.timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
            result = strict_json(response.text)
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("answers"), dict)
                or not set(questions).issubset(result["answers"])
            ):
                raise ValueError("Laya did not answer the typed questions")
            for identifier, question in questions.items():
                answer = result["answers"][identifier]
                if not isinstance(answer, dict):
                    raise ValueError("Laya answer must be a typed object")
                kind = question["type"]
                value = answer.get(kind)
                if kind == "choice":
                    if not isinstance(value, str) or value not in question["criteria"]:
                        raise ValueError("Laya choice is outside the declared criteria")
                elif (
                    isinstance(value, bool)
                    or not isinstance(value, (float, int))
                    or not 0 <= value <= (1 if kind == "noul" else len(question["criteria"]) - 1)
                ):
                    raise ValueError("Laya numeric answer violates its typed range")
            raw = result.get("usage", {})
            if (
                not isinstance(raw, dict)
                or (raw and not {"input_tokens", "output_tokens"}.issubset(raw))
                or any(
                    isinstance(raw.get(name, 0), bool)
                    or not isinstance(raw.get(name, 0), int)
                    or not 0 <= raw.get(name, 0) <= 2**63 - 1
                    for name in ("input_tokens", "output_tokens")
                )
            ):
                raise ValueError("Laya usage must contain nonnegative integer token counts")
            usage = Usage(
                input_tokens=raw.get("input_tokens", 0),
                output_tokens=raw.get("output_tokens", 0),
                cost_usd=config.cost_per_call_usd,
                latency_seconds=time.monotonic() - started,
                estimated=not bool(raw),
            )
            return result, usage
        except (httpx.HTTPError, ValueError, TypeError):
            raise ProviderError(
                "Laya request failed or violated its typed contract; use the reasoning model",
                usage=Usage(
                    cost_usd=config.cost_per_call_usd,
                    estimated=True,
                    latency_seconds=time.monotonic() - started,
                ),
            ) from None
        finally:
            if self.client is None:
                client.close()


def triage(
    store: Store, run_id: str, role: str, config: LayaConfig, state: dict[str, Any]
) -> dict[str, Any]:
    privacy = store.get_config(run_id).privacy
    state = redact(state, privacy.redact_patterns)
    key = hashlib.sha256(
        json.dumps(
            {"run": run_id, "role": role, "state": state, "config": config.model_dump()},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cached = store.cache_get(key) if privacy.cache else None
    if cached is not None:
        return cached
    call_id = store.reserve(run_id, "laya_triage", config.cost_per_call_usd, key)
    try:
        result, usage = LayaClient(config).decide(
            state,
            {
                "needs_deeper_analysis": {
                    "type": "noul",
                    "instructions": "Does this research decision involve unresolved evidence, conflicting results, novelty, causal or statistical interpretation that requires a full scientific reasoning agent?",
                }
            },
        )
    except (ProviderError, ValueError) as exc:
        usage = exc.usage if isinstance(exc, ProviderError) else Usage()
        store.settle(call_id, usage)
        store.event(
            run_id,
            "model_escalation",
            role,
            {
                "provider": "laya",
                "model": config.model,
                "reason": str(exc),
                "usage": usage.model_dump(),
            },
        )
        return {"available": False, "escalate": True, "reason": str(exc)}
    store.settle(call_id, usage)
    result.update(available=True, advisory_only=True)
    store.event(
        run_id,
        "agent_completed",
        role,
        {
            "role": "laya_triage",
            "provider": "laya",
            "model": config.model,
            "output": result,
            "usage": usage.model_dump(),
        },
    )
    if privacy.cache:
        store.cache_put(key, result)
    return result
