"""Native Anthropic Messages API transport built on the official ``anthropic`` SDK.

Selected by ``ProviderConfig.adapter == "anthropic"``. Behaviour mirrors
``CompatibleProvider``: Metis owns retries (the SDK's are disabled), quota
classification, accounting and the strict JSON-object contract. The SDK is imported
only when a request is made, so configuration checks and the PaperOrchestra writer
image never need it. Never pass objects from the ``httpx`` package to the SDK: the
1.x SDK is built on ``httpx2``.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .contracts import AgentRequest, AgentResponse, ProviderConfig, Usage
from .providers import (
    CompatibleProvider,
    ProviderError,
    _credential,
    _endpoint,
    overloaded,
    price_usage,
    quota_window,
    request_input_bound,
    retry_hint_seconds,
    strict_json,
)

# Metis ``reasoning_effort`` → Anthropic ``output_config.effort``. Anthropic has no level
# below ``low``; ``none``/``minimal`` (OpenAI names) map to it.
EFFORT = {
    "none": "low",
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}
_REQUEST_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_FENCE = re.compile(r"\A\s*```(?:json)?\s*\n(.*?)\n?```\s*\Z", re.S)


def _request_id(value: object) -> str:
    return value if isinstance(value, str) and _REQUEST_ID.fullmatch(value) else ""


def _unfence(text: str) -> str:
    """Remove one surrounding Markdown code fence; the content is still parsed strictly."""
    match = _FENCE.match(text)
    return match.group(1) if match else text


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**63 - 1:
        raise ValueError("Invalid token count")
    return value


class AnthropicProvider:
    """Anthropic Messages API transport (prompt caching, effort, strict JSON objects).

    Requests carry the Metis system prompt as a cached top-level ``system`` block,
    never an assistant prefill, tools or ``thinking`` configuration (current models
    think adaptively by default; Haiku 4.5 runs without thinking). ``temperature`` is
    sent only when ``config.send_temperature`` is set, because current models reject
    non-default sampling. Effort comes from ``config.reasoning_effort``.
    """

    def __init__(self, config: ProviderConfig, *, http_client: Any | None = None) -> None:
        if config.adapter != "anthropic":
            raise ProviderError("AnthropicProvider requires adapter 'anthropic'")
        self.config = config.model_copy(deep=True)
        self._local = _endpoint(config)
        effort = config.reasoning_effort
        if effort is not None and effort not in EFFORT:
            raise ProviderError(
                f"Unsupported reasoning effort {effort!r} for Anthropic; use one of "
                + ", ".join(sorted(set(EFFORT.values())))
            )
        # Tests inject an ``httpx2`` client with a mock transport.
        self._http_client = http_client
        self.progress: Callable[[dict[str, Any]], None] | None = None

    # ------------------------------------------------------------------ request shape

    def payload(self, request: AgentRequest) -> dict[str, Any]:
        """Keyword arguments for ``client.messages.create``/``.stream`` (no secrets)."""
        content: list[dict[str, Any]]
        if request.split_context:
            parts = CompatibleProvider._messages(request)[1:]
            content = [{"type": "text", "text": part["content"]} for part in parts]
            # The stable reference chunk (project and brief) is a second cache breakpoint.
            content[0]["cache_control"] = {"type": "ephemeral"}
        else:
            content = [{"type": "text", "text": request.prompt}]
        params: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_output_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if request.system:
            # Byte-stable system prompt first: the cached prefix (five-minute TTL).
            params["system"] = [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ]
        if self.config.reasoning_effort is not None:
            params["output_config"] = {"effort": EFFORT[self.config.reasoning_effort]}
        if self.config.send_temperature:
            # The 1.x SDK has no sampling keyword; models that accept it read the body field.
            params["extra_body"] = {"temperature": request.temperature}
        return params

    def _estimate(self, request: AgentRequest) -> Usage:
        return price_usage(
            self.config,
            request_input_bound(request),
            self.config.max_output_tokens,
            estimated=True,
        )

    def _reported(self, raw: Any) -> Usage:
        """Anthropic ``input_tokens`` exclude cache reads and writes; Metis counts all input."""
        uncached = _count(getattr(raw, "input_tokens", None))
        written = _count(getattr(raw, "cache_creation_input_tokens", None) or 0)
        read = _count(getattr(raw, "cache_read_input_tokens", None) or 0)
        outputs = _count(getattr(raw, "output_tokens", None))
        usage = price_usage(
            self.config, uncached + written + read, outputs, cached=read, cache_write=written
        )
        usage.cached_input_tokens = read
        return usage

    # ------------------------------------------------------------------ transport

    def _client(self, key: str) -> Any:
        import anthropic

        timeout = anthropic.Timeout(
            self.config.timeout_seconds, connect=min(30, self.config.timeout_seconds)
        )
        # No ambient proxies or redirects: the credential must not move to another host.
        http_client = self._http_client or anthropic.DefaultHttpxClient(
            trust_env=False, follow_redirects=False, timeout=timeout
        )
        return anthropic.Anthropic(
            # A keyless loopback server still needs a header value; never another source.
            api_key=key or "loopback-no-key",
            base_url=self.config.base_url.rstrip("/"),
            max_retries=0,  # Metis applies its own bounded retry and fallback policy.
            timeout=timeout,
            http_client=http_client,
        )

    def _emitter(self, attempt: int) -> Callable[..., None]:
        state = {"last": 0.0}

        def emit(status: str, *, force: bool = False, **extra: Any) -> None:
            now = time.monotonic()
            if self.progress and (force or now - state["last"] >= 5):
                self.progress({"status": status, "attempt": attempt, **extra})
                state["last"] = now

        return emit

    def _stream(self, client: Any, params: dict[str, Any], estimate: Usage, attempt: int) -> Any:
        """Stream the message; errors before the first event propagate as SDK errors."""
        emit = self._emitter(attempt)
        with client.messages.stream(**params) as stream:
            text: list[str] = []
            status = "waiting"
            response_id = ""
            stopped = False
            try:
                for event in stream:
                    previous = status
                    kind = getattr(event, "type", "")
                    if kind == "message_stop":
                        stopped = True
                    elif kind == "message_start":
                        response_id = _request_id(getattr(event.message, "id", ""))
                    elif kind == "content_block_start":
                        block = getattr(event.content_block, "type", "")
                        if block == "thinking" and not text:
                            status = "reasoning"
                    elif kind == "content_block_delta" and event.delta.type == "text_delta":
                        text.append(event.delta.text)
                        status = "receiving"
                    emit(
                        status,
                        force=status != previous,
                        response_id=response_id,
                        answer_chars=sum(map(len, text)),
                    )
                if not stopped:
                    raise ValueError("Stream ended without message_stop")
                message = stream.get_final_message()
            except Exception:
                emit(
                    "interrupted",
                    force=True,
                    response_id=response_id,
                    answer_chars=sum(map(len, text)),
                    output="".join(text),
                )
                # The server began this response; its remote outcome is unknown. Never
                # resubmit or switch models blindly. Partial output stays diagnostic.
                raise ProviderError(
                    "Provider stream interrupted or incomplete; received output is saved in traces, not accepted. Remote completion is unknown; inspect before retrying.",
                    usage=Usage(
                        input_tokens=estimate.input_tokens,
                        output_tokens=estimate.output_tokens,
                        cost_usd=estimate.cost_usd,
                        estimated=True,
                    ),
                    model=self.config.model,
                ) from None
            emit(
                "received",
                force=True,
                response_id=response_id,
                answer_chars=sum(map(len, text)),
                output="".join(text),
            )
            return message

    def complete(self, request: AgentRequest) -> AgentResponse:
        import anthropic

        key = _credential(self.config, self._local)
        params = self.payload(request)
        estimate = self._estimate(request)
        started = time.monotonic()
        total = Usage(cached_input_tokens=0)

        def accrue(usage: Usage) -> None:
            total.cached_input_tokens = (
                total.cached_input_tokens + usage.cached_input_tokens
                if total.cached_input_tokens is not None and usage.cached_input_tokens is not None
                else None
            )
            total.input_tokens += usage.input_tokens
            total.output_tokens += usage.output_tokens
            total.cost_usd += usage.cost_usd
            total.estimated = total.estimated or usage.estimated
            total.latency_seconds = time.monotonic() - started

        client = self._client(key)
        model = self.config.model
        try:
            for attempt in range(self.config.retries + 1):
                if self.progress:
                    self.progress({"status": "waiting", "attempt": attempt})
                try:
                    if self.config.streaming:
                        message = self._stream(client, params, estimate, attempt)
                    else:
                        message = client.messages.create(**params)
                except ProviderError as error:
                    accrue(error.usage)
                    error.usage = total
                    raise
                except anthropic.APIStatusError as exc:
                    # Error responses report no usage: settle the conservative estimate.
                    accrue(estimate)
                    self._status_error(exc, total, attempt)
                    continue
                except anthropic.APIConnectionError:
                    # Includes timeouts. No response receipt: billing is uncertain.
                    accrue(estimate)
                    if attempt == self.config.retries:
                        raise ProviderError(
                            "Provider transport failed", usage=total, recoverable=True, model=model
                        ) from None
                    time.sleep(min(2**attempt, 8))
                    continue
                except anthropic.AnthropicError as exc:
                    accrue(estimate)
                    raise ProviderError(
                        f"Anthropic client error ({type(exc).__name__})", usage=total, model=model
                    ) from None
                return self._response(message, total, accrue)
            raise AssertionError("Retry loop exhausted without result")
        finally:
            client.close()

    def _status_error(self, exc: Any, total: Usage, attempt: int) -> None:
        """Raise for final or non-retryable statuses; otherwise sleep before the next attempt."""
        status = int(exc.status_code)
        headers = {k.lower(): v for k, v in exc.response.headers.items()}
        body = exc.body
        request_id = _request_id(getattr(exc, "request_id", None))
        details = {"request_id": request_id} if request_id else {}
        error_type = getattr(exc, "type", None)
        label = f"HTTP {status}" + (f" {error_type}" if isinstance(error_type, str) else "")
        suffix = f"; request {request_id}" if request_id else ""
        model = self.config.model
        error = body.get("error") if isinstance(body, dict) else None
        code = (error.get("details") or {}).get("error_code") if isinstance(error, dict) else None
        if status == 429 and code == "enforced_spend_limit_reached":
            # Spend cap: waiting for a rate-limit window cannot help; another model may.
            raise ProviderError(
                f"Anthropic spend cap reached ({label}{suffix}); requests fail until access resumes",
                usage=total,
                recoverable=True,
                model=model,
                details=details,
            )
        # 529 overloaded_error is Anthropic's transient high-demand signal, like Gemini 503.
        limited = status in {429, 529} or overloaded(status, body)
        hint = retry_hint_seconds(headers, body) if limited else None
        if status == 429:
            window, reset, quota = quota_window(headers, body, hint)
            if window == "long":
                until = datetime.now(UTC) + timedelta(seconds=reset or 0.0)
                raise ProviderError(
                    f"Provider quota exhausted (HTTP 429); model unavailable "
                    f"until {until.isoformat(timespec='seconds')}{suffix}",
                    usage=total,
                    recoverable=True,
                    rate_limited=True,
                    retry_after_seconds=reset,
                    model=model,
                    quota_exhausted_until=until.isoformat(),
                    quota={**quota, "window": "long"},
                    details=details,
                )
        elif status < 500:
            # 400/401/403/404/413 and similar: configuration or request errors.
            raise ProviderError(
                f"Provider request rejected ({label}{suffix})",
                usage=total,
                model=model,
                details=details,
            )
        if attempt == self.config.retries:
            raise ProviderError(
                f"Provider failed after retries ({label}{suffix})",
                usage=total,
                recoverable=True,
                rate_limited=limited,
                retry_after_seconds=hint,
                model=model,
                details=details,
            )
        delay = float(min(2**attempt, 8))
        if hint is not None:
            delay = max(delay, min(hint, 30))
        time.sleep(delay)

    def _response(
        self, message: Any, total: Usage, accrue: Callable[[Usage], None]
    ) -> AgentResponse:
        request_id = _request_id(getattr(message, "_request_id", None))
        details = {"request_id": request_id} if request_id else {}
        try:
            usage = self._reported(message.usage)
        except (AttributeError, ValueError):
            usage = None
        if usage is None:
            raise ProviderError(
                "Provider response lacked valid usage", usage=total, model=self.config.model
            )
        accrue(usage)
        stop = getattr(message, "stop_reason", None)
        if stop == "refusal":
            category = getattr(getattr(message, "stop_details", None), "category", None)
            category = str(category)[:80] if category else "unspecified"
            raise ProviderError(
                f"Anthropic declined the request (stop_reason refusal, category {category}); "
                "no output was accepted",
                usage=total,
                model=self.config.model,
                details={**details, "refusal_category": category},
            )
        try:
            if stop not in {"end_turn", "stop_sequence"}:
                # max_tokens (truncated), pause_turn or tool_use cannot be a complete answer.
                raise ValueError("Incomplete response")
            text = "".join(
                block.text for block in message.content if getattr(block, "type", "") == "text"
            )
            data = strict_json(_unfence(text))
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
        except (TypeError, ValueError, RecursionError):
            raise ProviderError(
                "Provider returned an invalid or truncated JSON object",
                usage=total,
                model=self.config.model,
                details=details,
            ) from None
        return AgentResponse(
            data=data, usage=total, model=self.config.model, provider=self.config.name
        )
