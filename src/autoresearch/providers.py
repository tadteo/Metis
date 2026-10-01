"""Small, replaceable model transport with explicit credentials and bounded retries."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from .contracts import AgentRequest, AgentResponse, ProviderConfig, Usage
from .credentials import CredentialAccessError, resolve


class Provider(Protocol):
    def complete(self, request: AgentRequest) -> AgentResponse: ...


class ProviderError(RuntimeError):
    """Safe diagnostic plus the usage incurred before the failure.

    Callers must settle this usage against their reservation even when no valid
    agent response was produced. Unreported usage is deliberately overestimated.
    """

    def __init__(
        self, message: str, *, usage: Usage | None = None, recoverable: bool = False
    ) -> None:
        super().__init__(message)
        self.usage = usage or Usage()
        self.recoverable = recoverable


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

    Credentials use the configured name as a lookup reference. Redirects and
    ambient HTTP proxy configuration are disabled so
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
        self.progress: Callable[[dict[str, Any]], None] | None = None

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

    def _read_stream(
        self, response: httpx.Response, estimate: Usage, attempt: int
    ) -> dict[str, Any]:
        """Assemble SSE, preserving partial answers without accepting partial research."""
        content: list[str] = []
        fields: list[str] = []
        usage: dict[str, Any] = {}
        response_id = ""
        finish = None
        count = 0
        size = 0
        status = "waiting"
        last_emitted = 0.0

        def emit(*, force: bool = False) -> None:
            nonlocal last_emitted
            now = time.monotonic()
            if self.progress and (force or now - last_emitted >= 5):
                self.progress(
                    {
                        "status": status,
                        "attempt": attempt,
                        "response_id": response_id,
                        "answer_chars": count,
                        **(
                            {"output": "".join(content)}
                            if status in {"received", "interrupted"}
                            else {}
                        ),
                    }
                )
                last_emitted = now

        try:
            for line in response.iter_lines():
                size += len(line.encode())
                if size > 16 * 1024 * 1024:
                    raise ValueError("Stream too large")
                if line.startswith(":"):
                    emit()
                    continue
                if line:
                    if line.startswith("data:"):
                        fields.append(line[5:].removeprefix(" "))
                    continue
                if not fields:
                    continue
                raw = "\n".join(fields)
                fields.clear()
                if raw == "[DONE]":
                    if finish != "stop":
                        raise ValueError("Missing successful finish")
                    status = "received"
                    emit(force=True)
                    return {
                        "choices": [
                            {"message": {"content": "".join(content)}, "finish_reason": finish}
                        ],
                        **usage,
                    }
                chunk = strict_json(raw)
                if not isinstance(chunk, dict) or "error" in chunk:
                    raise ValueError("Invalid stream event")
                identifier = chunk.get("id")
                if isinstance(identifier, str) and re.fullmatch(
                    r"[A-Za-z0-9_.:-]{1,256}", identifier
                ):
                    response_id = identifier
                # Providers may repeat cumulative usage; use the latest total, never sum chunks.
                if isinstance(chunk.get("usage"), dict):
                    usage = {"usage": chunk["usage"]}
                previous = status
                for choice in chunk.get("choices", []):
                    if choice.get("index", 0) != 0:
                        raise ValueError("Unexpected choice")
                    delta = choice.get("delta", {})
                    answer = delta.get("content")
                    if answer is not None and not isinstance(answer, str):
                        raise ValueError("Invalid answer delta")
                    if answer:
                        content.append(answer)
                        count += len(answer)
                        status = "receiving"
                    elif delta.get("reasoning_content") and not content:
                        status = "reasoning"
                    if choice.get("finish_reason") is not None:
                        finish = choice["finish_reason"]
                emit(force=status != previous)
            raise ValueError("Stream ended without completion")
        except (httpx.TransportError, ValueError, TypeError, AttributeError, RecursionError):
            status = "interrupted"
            emit(force=True)
            # The server has begun this response. Do not blindly submit it again or switch
            # models while its remote outcome is unknown. Partial output remains diagnostic.
            reported = self._reported_usage(usage, estimate)
            conservative = Usage(
                input_tokens=max(reported.input_tokens, estimate.input_tokens),
                output_tokens=max(reported.output_tokens, estimate.output_tokens),
                cost_usd=max(reported.cost_usd, estimate.cost_usd),
                estimated=True,
            )
            raise ProviderError(
                "Provider stream interrupted or incomplete; received output is saved in traces, not accepted. Remote completion is unknown; inspect before retrying.",
                usage=conservative,
            ) from None

    def complete(self, request: AgentRequest) -> AgentResponse:
        try:
            key, _ = resolve(self.config.api_key_env)
        except CredentialAccessError as exc:
            raise ProviderError(str(exc)) from None
        if not key and not self._local:
            raise ProviderError(
                f"Provider credential is missing; connect {self.config.api_key_env} in Metis or set it in the environment"
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
            "stream": self.config.streaming,
        }
        if self.config.streaming:
            payload["stream_options"] = {"include_usage": True}
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
                if self.progress:
                    self.progress({"status": "waiting", "attempt": attempt})
                body: dict[str, Any] = {}
                try:
                    with client.stream(
                        "POST",
                        self._url,
                        json=payload,
                        headers=headers,
                        timeout=httpx.Timeout(
                            self.config.timeout_seconds,
                            connect=min(30, self.config.timeout_seconds),
                        ),
                        follow_redirects=False,
                    ) as response:
                        if response.is_success and "text/event-stream" in response.headers.get(
                            "content-type", ""
                        ):
                            body = self._read_stream(response, estimate, attempt)
                        else:
                            response.read()
                            try:
                                parsed = strict_json(response.text)
                                if isinstance(parsed, dict):
                                    body = parsed
                            except (ValueError, RecursionError):
                                pass
                except ProviderError as error:
                    accrue(error.usage)
                    error.usage = total
                    raise
                except httpx.TransportError:
                    # No response receipt: billing is uncertain, never silently zero.
                    accrue(estimate)
                    if attempt == self.config.retries:
                        raise ProviderError(
                            "Provider transport failed", usage=total, recoverable=True
                        ) from None
                    time.sleep(min(2**attempt, 8))
                    continue
                accrue(self._reported_usage(body, estimate))
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    if attempt == self.config.retries:
                        raise ProviderError(
                            f"Provider failed after retries (HTTP {response.status_code})",
                            usage=total,
                            recoverable=True,
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
