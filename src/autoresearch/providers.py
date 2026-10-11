"""Small, replaceable model transport with explicit credentials and bounded retries."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
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
        self,
        message: str,
        *,
        usage: Usage | None = None,
        recoverable: bool = False,
        rate_limited: bool = False,
        retry_after_seconds: float | None = None,
        model: str = "",
        quota_exhausted_until: str = "",
        quota: Mapping[str, str] | None = None,
        details: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage or Usage()
        self.recoverable = recoverable
        # Only HTTP 429 or 503 UNAVAILABLE sets this; the sole trigger for opt-in quota waiting.
        self.rate_limited = rate_limited
        self.retry_after_seconds = retry_after_seconds
        self.model = model
        # Absolute UTC ISO time before which a long-window quota (e.g. per day) stays exhausted.
        self.quota_exhausted_until = quota_exhausted_until
        self.quota: dict[str, str] = dict(quota or {})
        # Bounded diagnostics such as a provider request id or a refusal category.
        self.details: dict[str, str] = dict(details or {})


class RequestTooLarge(ProviderError):
    """Pre-dispatch refusal: the request exceeds a model's declared token limits.

    No request was sent and nothing was charged. Fallback may try another model;
    when none fits the run blocks instead of waiting for a quota that cannot help.
    """


def _errors(body: Any) -> list[dict[str, Any]]:
    items = body if isinstance(body, list) else [body]
    return [
        item["error"]
        for item in items[:4]
        if isinstance(item, dict) and isinstance(item.get("error"), dict)
    ]


def billing_exhausted(body: Any) -> bool:
    """OpenAI-style 429 for exhausted credit; waiting cannot fix it, so it never waits."""
    return any(
        "insufficient_quota" in (error.get("code"), error.get("type")) for error in _errors(body)
    )


def overloaded(status_code: int, body: Any) -> bool:
    """Gemini's transient high-demand response: HTTP 503 with error status UNAVAILABLE."""
    if status_code != 503:
        return False
    return any(error.get("status") == "UNAVAILABLE" for error in _errors(body))


_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")


def retry_hint_seconds(headers: Mapping[str, str], body: Any) -> float | None:
    """Provider-advertised wait from Retry-After or Google's RetryInfo, if any."""
    hints: list[float] = []
    raw = headers.get("retry-after", "").strip()
    if raw:
        try:
            hints.append(float(raw))
        except ValueError:
            try:
                moment = parsedate_to_datetime(raw)
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=UTC)
                hints.append((moment - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
    # Gemini may wrap the error object in a one-element list.
    items = body if isinstance(body, list) else [body]
    for item in items[:4]:
        error = item.get("error") if isinstance(item, dict) else None
        details = error.get("details") if isinstance(error, dict) else None
        for detail in details[:16] if isinstance(details, list) else []:
            delay = detail.get("retryDelay") if isinstance(detail, dict) else None
            match = _DURATION.match(delay) if isinstance(delay, str) else None
            if match:
                hints.append(float(match.group(1)))
    finite = [max(0.0, hint) for hint in hints if math.isfinite(hint)]
    return max(finite) if finite else None


# Rate-limit windows at or below this many seconds are short (requests/tokens per minute)
# and keep the provider's bounded in-request retries. Longer windows mean quota exhaustion.
SHORT_WINDOW_SECONDS = 60.0
# A daily quota without an advertised reset is re-probed (with one request) after this delay.
UNKNOWN_RESET_SECONDS = 3600.0
_LONG_MARKERS = ("perday", "per_day", "daily", "perweek", "permonth")
_RESET = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def _reset_seconds(raw: str) -> float | None:
    """OpenAI-style reset header ("6m0s", "1h2m3.5s", "20ms", or plain seconds)."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) and value >= 0 else None
    except ValueError:
        pass
    parts = _RESET.findall(raw)
    if not parts or "".join(number + unit for number, unit in parts) != raw:
        return None
    scale = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(number) * scale[unit] for number, unit in parts)


def _until_seconds(raw: str) -> float | None:
    """Seconds from now until an RFC 3339 timestamp (never negative); None if unparsable."""
    raw = raw.strip()
    if not raw or len(raw) > 64:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - datetime.now(UTC)).total_seconds())


def quota_violations(body: Any) -> list[dict[str, str]]:
    """Google ``google.rpc.QuotaFailure`` violations, as bounded plain strings."""
    found: list[dict[str, str]] = []
    for error in _errors(body):
        details = error.get("details")
        for detail in details[:16] if isinstance(details, list) else []:
            if not isinstance(detail, dict) or not str(detail.get("@type", "")).endswith(
                "QuotaFailure"
            ):
                continue
            violations = detail.get("violations")
            for violation in violations[:16] if isinstance(violations, list) else []:
                if isinstance(violation, dict):
                    found.append(
                        {
                            key: str(violation[source])[:200]
                            for key, source in (
                                ("quota_id", "quotaId"),
                                ("quota_metric", "quotaMetric"),
                                ("quota_value", "quotaValue"),
                            )
                            if isinstance(violation.get(source), (str, int))
                        }
                    )
    return found


def quota_window(
    headers: Mapping[str, str], body: Any, hint: float | None
) -> tuple[str, float | None, dict[str, str]]:
    """Classify a rate limit as ``short`` (per-minute) or ``long`` (e.g. per-day exhaustion).

    Returns the window, the seconds until the limit resets (if known) and quota
    metadata. Long: an advertised wait above ``SHORT_WINDOW_SECONDS``, a Google
    QuotaFailure whose quota id names a daily (or longer) window, or an
    OpenAI-style ``x-ratelimit-remaining-*: 0`` whose reset is beyond the short window.
    """
    violations = quota_violations(body)
    daily = [
        item
        for item in violations
        if any(marker in item.get("quota_id", "").lower() for marker in _LONG_MARKERS)
    ]
    quota = dict((daily or violations or [{}])[0])
    reset = hint
    header_reset: float | None = None
    for kind in ("requests", "tokens", "input-tokens", "output-tokens"):
        # Anthropic: anthropic-ratelimit-<kind>-remaining/-limit and an RFC 3339 -reset.
        remaining = headers.get(f"anthropic-ratelimit-{kind}-remaining", "").strip()
        seconds = _until_seconds(headers.get(f"anthropic-ratelimit-{kind}-reset", ""))
        if remaining == "0" and seconds is not None:
            header_reset = max(header_reset or 0.0, seconds)
            quota.setdefault("quota_id", f"anthropic-ratelimit-{kind}")
            limit = headers.get(f"anthropic-ratelimit-{kind}-limit", "").strip()[:40]
            if limit:
                quota.setdefault("quota_value", limit)
    for kind in ("requests", "tokens"):
        remaining = headers.get(f"x-ratelimit-remaining-{kind}", "").strip()
        seconds = _reset_seconds(headers.get(f"x-ratelimit-reset-{kind}", ""))
        if remaining == "0" and seconds is not None:
            header_reset = max(header_reset or 0.0, seconds)
            quota.setdefault("quota_id", f"x-ratelimit-{kind}")
            limit = headers.get(f"x-ratelimit-limit-{kind}", "").strip()[:40]
            if limit:
                quota.setdefault("quota_value", limit)
    if reset is None:
        reset = header_reset
    elif header_reset is not None:
        reset = max(reset, header_reset)
    long = bool(daily) or (reset is not None and reset > SHORT_WINDOW_SECONDS)
    if daily:
        # A daily quota cannot reset within seconds; a short advertised delay would
        # only cause rapid probes. Wait at least the documented re-probe delay.
        reset = max(reset or 0.0, UNKNOWN_RESET_SECONDS)
    elif long and reset is None:
        reset = UNKNOWN_RESET_SECONDS
    return ("long" if long else "short"), reset, quota


# Anthropic bills five-minute prompt-cache writes at 1.25 times the base input price.
CACHE_WRITE_MULTIPLIER = 1.25


def price_usage(
    config: ProviderConfig,
    inputs: int,
    outputs: int,
    *,
    estimated: bool = False,
    cached: int = 0,
    cache_write: int = 0,
) -> Usage:
    """Charge for reported tokens. ``inputs`` includes ``cached`` reads and ``cache_write``s.

    Cache reads use ``cached_input_per_million`` (scaled like input above the long-context
    threshold) when configured, else the full input rate. Cache writes (Anthropic's five-minute cache) cost 1.25 times the input rate.
    """
    long = inputs > config.long_context_threshold or estimated
    input_rate = (
        max(config.input_per_million, config.long_input_per_million)
        if long
        else config.input_per_million
    )
    output_rate = (
        max(config.output_per_million, config.long_output_per_million)
        if long
        else config.output_per_million
    )
    cached = min(max(cached, 0), inputs)
    cache_write = min(max(cache_write, 0), inputs - cached)
    read_rate = input_rate
    if config.cached_input_per_million is not None:
        # Long-context surcharges scale cache reads by the same factor as input
        # (OpenAI, Gemini Pro and Haiku 5.5 publish it that way).
        scale = input_rate / config.input_per_million if config.input_per_million else 1.0
        read_rate = config.cached_input_per_million * scale
    plain = inputs - cached - cache_write
    cost = (
        plain * input_rate
        + cached * min(read_rate, input_rate)
        + cache_write * input_rate * CACHE_WRITE_MULTIPLIER
        + outputs * output_rate
    )
    return Usage(
        input_tokens=inputs,
        output_tokens=outputs,
        cost_usd=cost / 1_000_000,
        estimated=estimated,
    )


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


def _endpoint(config: ProviderConfig) -> bool:
    """Validate the endpoint and key-variable name; return whether the host is loopback."""
    parts = urlsplit(config.base_url)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.scheme not in {"https", "http"}
        or (parts.scheme != "https" and not local)
    ):
        raise ProviderError("Provider URL must use HTTPS (HTTP is allowed only on loopback)")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config.api_key_env):
        raise ProviderError("Invalid provider credential environment variable name")
    return local


def _credential(config: ProviderConfig, local: bool) -> str:
    try:
        key, _ = resolve(config.api_key_env)
    except CredentialAccessError as exc:
        raise ProviderError(str(exc)) from None
    if not key and not local:
        raise ProviderError(
            f"Provider credential is missing; connect {config.api_key_env} in Metis or set it in the environment"
        )
    if not key.isascii() or any(char.isspace() for char in key):
        raise ProviderError("Provider credential contains invalid characters")
    return key


class CompatibleProvider:
    """OpenAI chat-completions transport, including xAI and local endpoints.

    Credentials use the configured name as a lookup reference. Redirects and
    ambient HTTP proxy configuration are disabled so
    credentials cannot silently move to another host.
    """

    def __init__(self, config: ProviderConfig, *, client: httpx.Client | None = None) -> None:
        self.config = config.model_copy(deep=True)
        self._local = _endpoint(config)
        self._url = config.base_url.rstrip("/") + "/chat/completions"
        self._client = client
        self.progress: Callable[[dict[str, Any]], None] | None = None

    @staticmethod
    def _messages(request: AgentRequest) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": request.system}]
        if not request.split_context:
            return messages + [{"role": "user", "content": request.prompt}]
        context = json.loads(request.prompt)
        state = context["state"]
        reference_fields = (
            "id",
            "title",
            "objective",
            "materials",
            "research_brief",
            "research_protocol",
            "baseline",
        )
        # Keep append-only evidence in stable chunks; changes invalidate affected prefixes.
        references = {
            "project": context["project"],
            "state": {key: state[key] for key in reference_fields if key in state},
        }
        current = {
            **{key: value for key, value in context.items() if key != "project"},
            "state": {
                key: value
                for key, value in state.items()
                if key not in (*reference_fields, "evidence")
            },
        }
        parts = [references]
        if "evidence" in state:
            evidence = state["evidence"]
            parts.extend(
                {"state": {"evidence": evidence[start : start + 8]}}
                for start in range(0, max(1, len(evidence)), 8)
            )
        parts.append(current)
        return messages + [{"role": "user", "content": json.dumps(part)} for part in parts]

    def _estimate(self, request: AgentRequest) -> Usage:
        # Byte length is an intentionally conservative token bound, including
        # enough overhead for chat framing. Budget reservations use the same rule.
        count = request_input_bound(request)
        return self._usage(count, self.config.max_output_tokens, estimated=True)

    def _usage(
        self, inputs: int, outputs: int, *, estimated: bool = False, cached: int = 0
    ) -> Usage:
        return price_usage(self.config, inputs, outputs, estimated=estimated, cached=cached)

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
        details = raw.get("prompt_tokens_details", raw.get("input_tokens_details"))
        cached = details.get("cached_tokens") if isinstance(details, dict) else None
        if cached is None:
            # DeepSeek reports prefix-cache hits as a top-level count.
            cached = raw.get("prompt_cache_hit_tokens")
        if isinstance(cached, int) and not isinstance(cached, bool) and 0 <= cached <= inputs:
            usage = self._usage(inputs, outputs, cached=cached)
            usage.cached_input_tokens = cached
            return usage
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
        key = _credential(self.config, self._local)
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if urlsplit(self._url).hostname == "api.x.ai":
            # Server affinity is stable across changing prompts, unlike response cache keys.
            identity = [request.run_id, request.role, self.config.model, request.system]
            headers["x-grok-conv-id"] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": self._messages(request),
            self.config.max_tokens_field: self.config.max_output_tokens,
            "stream": self.config.streaming,
        }
        if self.config.send_temperature:
            payload["temperature"] = request.temperature
        if self.config.streaming:
            payload["stream_options"] = {"include_usage": True}
        if self.config.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort
        started = time.monotonic()
        total = Usage(cached_input_tokens=0)
        estimate = self._estimate(request)

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

        client = self._client or httpx.Client(trust_env=False)
        try:
            for attempt in range(self.config.retries + 1):
                if self.progress:
                    self.progress({"status": "waiting", "attempt": attempt})
                body: dict[str, Any] = {}
                raw_body: Any = None
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
                                raw_body = parsed
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
                    # 429 and the provider's explicit overload signal are capacity limits.
                    limited = (
                        response.status_code == 429 and not billing_exhausted(raw_body)
                    ) or overloaded(response.status_code, raw_body)
                    hint = retry_hint_seconds(response.headers, raw_body) if limited else None
                    if limited and response.status_code == 429:
                        window, reset, quota = quota_window(response.headers, raw_body, hint)
                        if window == "long":
                            # Retrying inside this request cannot succeed before the reset
                            # and would spend scarce daily requests: stop after one attempt.
                            until = datetime.now(UTC) + timedelta(seconds=reset or 0.0)
                            raise ProviderError(
                                f"Provider quota exhausted (HTTP 429); model unavailable "
                                f"until {until.isoformat(timespec='seconds')}",
                                usage=total,
                                recoverable=True,
                                rate_limited=True,
                                retry_after_seconds=reset,
                                model=self.config.model,
                                quota_exhausted_until=until.isoformat(),
                                quota={**quota, "window": "long"},
                            )
                    if attempt == self.config.retries:
                        raise ProviderError(
                            f"Provider failed after retries (HTTP {response.status_code})",
                            usage=total,
                            recoverable=True,
                            rate_limited=limited,
                            retry_after_seconds=hint,
                            model=self.config.model,
                        )
                    delay = float(min(2**attempt, 8))
                    if hint is not None:
                        delay = max(delay, min(hint, 30))
                    else:
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


def request_input_bound(request: AgentRequest) -> int:
    """Conservative byte bound shared by admission and unknown-usage settlement."""
    if not request.split_context:
        return len(request.system.encode()) + len(request.prompt.encode()) + 256
    messages = CompatibleProvider._messages(request)
    return sum(len(message["content"].encode()) + 32 for message in messages) + 256


def create_provider(config: ProviderConfig) -> Provider:
    """The transport for ``config.adapter``. Construction validates without network access."""
    if config.adapter == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(config)
    return CompatibleProvider(config)
