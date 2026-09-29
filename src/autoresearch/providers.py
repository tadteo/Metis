"""Small, replaceable model transport with explicit credentials and bounded retries."""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from .contracts import AgentRequest, AgentResponse, ProviderConfig, Usage


class Provider(Protocol):
    def complete(self, request: AgentRequest) -> AgentResponse: ...


class ProviderError(RuntimeError):
    """Safe diagnostic plus the usage incurred before the failure.

    Callers must settle this usage against their reservation even when no valid
    agent response was produced. Unreported usage is deliberately overestimated.
    """

    def __init__(self, message: str, *, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or Usage()


def strict_json(text: str) -> Any:
    """Reject ambiguous duplicate keys and non-standard NaN/Infinity values."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_: str) -> Any:
        raise ValueError("Non-finite JSON value")

    def decimal(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON value")
        return number

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=decimal)


class CompatibleProvider:
    """OpenAI chat-completions transport, including xAI and local endpoints.

    Credentials come exclusively from the explicitly configured environment
    variable. Redirects and ambient HTTP proxy configuration are disabled so
    credentials cannot silently move to another host.
    """

    def __init__(self, config: ProviderConfig, *, client: httpx.Client | None = None) -> None:
        self.config = config.model_copy(deep=True)
        parts = urlsplit(config.base_url)
        self._local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or parts.scheme not in {"https", "http"}
            or (parts.scheme != "https" and not self._local)
        ):
            raise ProviderError("Provider URL must use HTTPS (HTTP is allowed only on loopback)")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config.api_key_env):
            raise ProviderError("Invalid provider credential environment variable name")
        self._url = config.base_url.rstrip("/") + "/chat/completions"
        self._client = client

    def _estimate(self, request: AgentRequest) -> Usage:
        # Byte length is an intentionally conservative token bound, including
        # enough overhead for chat framing. Budget reservations use the same rule.
        count = len(request.system.encode()) + len(request.prompt.encode()) + 256
        return self._usage(count, self.config.max_output_tokens, estimated=True)

    def _usage(self, inputs: int, outputs: int, *, estimated: bool = False) -> Usage:
        long = inputs > self.config.long_context_threshold or estimated
        input_rate = (
            max(self.config.input_per_million, self.config.long_input_per_million)
            if long
            else self.config.input_per_million
        )
        output_rate = (
            max(self.config.output_per_million, self.config.long_output_per_million)
            if long
            else self.config.output_per_million
        )
        return Usage(
            input_tokens=inputs,
            output_tokens=outputs,
            cost_usd=(inputs * input_rate + outputs * output_rate) / 1_000_000,
            estimated=estimated,
        )

    def _reported_usage(self, body: Mapping[str, Any], fallback: Usage) -> Usage:
        raw = body.get("usage")
        if not isinstance(raw, dict):
            return fallback
        inputs = raw.get("prompt_tokens", raw.get("input_tokens"))
        outputs = raw.get("completion_tokens", raw.get("output_tokens"))
        if (
            isinstance(inputs, bool)
            or isinstance(outputs, bool)
            or not isinstance(inputs, int)
            or not isinstance(outputs, int)
            or inputs < 0
            or outputs < 0
            or inputs > 2**63 - 1
            or outputs > 2**63 - 1
        ):
            return fallback
        return self._usage(inputs, outputs)

    def complete(self, request: AgentRequest) -> AgentResponse:
        key = os.environ.get(self.config.api_key_env, "")
        if not key and not self._local:
            raise ProviderError(
                f"Provider credential is missing; set {self.config.api_key_env} in the environment"
            )
        if not key.isascii() or any(char.isspace() for char in key):
            raise ProviderError("Provider credential contains invalid characters")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": self.config.max_output_tokens,
            "stream": False,
        }
        if self.config.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort
        started = time.monotonic()
        total = Usage()
        estimate = self._estimate(request)

        def accrue(usage: Usage) -> None:
            total.input_tokens += usage.input_tokens
            total.output_tokens += usage.output_tokens
            total.cost_usd += usage.cost_usd
            total.estimated = total.estimated or usage.estimated
            total.latency_seconds = time.monotonic() - started

        client = self._client or httpx.Client(trust_env=False)
        try:
            for attempt in range(self.config.retries + 1):
                try:
                    response = client.post(
                        self._url,
                        json=payload,
                        headers=headers,
                        timeout=self.config.timeout_seconds,
                        follow_redirects=False,
                    )
                except httpx.TransportError:
                    # A timeout/disconnect can occur after the server has billed
                    # the request. Never silently turn that into zero usage.
                    accrue(estimate)
                    if attempt == self.config.retries:
                        raise ProviderError("Provider transport failed", usage=total) from None
                    time.sleep(min(2**attempt, 8))
                    continue
                body: dict[str, Any] = {}
                try:
                    parsed = strict_json(response.text)
                    if isinstance(parsed, dict):
                        body = parsed
                except (ValueError, RecursionError):
                    pass
                accrue(self._reported_usage(body, estimate))
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    if attempt == self.config.retries:
                        raise ProviderError(
                            f"Provider failed after retries (HTTP {response.status_code})",
                            usage=total,
                        )
                    delay = float(min(2**attempt, 8))
                    try:
                        retry_after = float(response.headers.get("retry-after", "0"))
                        if math.isfinite(retry_after):
                            delay = max(delay, min(max(retry_after, 0), 30))
                    except ValueError:
                        pass
                    time.sleep(delay)
                    continue
                if response.status_code < 200 or response.status_code >= 300:
                    raise ProviderError(
                        f"Provider request rejected (HTTP {response.status_code})", usage=total
                    )
                try:
                    content = body["choices"][0]["message"]["content"]
                    if not isinstance(content, str):
                        raise ValueError("Expected JSON text")
                    data = strict_json(content)
                    if not isinstance(data, dict):
                        raise ValueError("Expected JSON object")
                    if body["choices"][0].get("finish_reason") == "length":
                        raise ValueError("Truncated response")
                except (KeyError, IndexError, TypeError, ValueError, RecursionError):
                    raise ProviderError(
                        "Provider returned an invalid or truncated JSON object", usage=total
                    ) from None
                return AgentResponse(
                    data=data, usage=total, model=self.config.model, provider=self.config.name
                )
            raise AssertionError("Retry loop exhausted without result")
        finally:
            if self._client is None:
                client.close()
