"""Opt-in waiting for provider quota after HTTP 429, shared by the engine and status views."""

from __future__ import annotations

from datetime import datetime

from .config import QuotaWaitConfig
from .providers import ProviderError

POLL_SECONDS = 10.0


def rate_limit_error(exc: BaseException) -> ProviderError | None:
    """Find a rate-limited ProviderError behind a stage failure, as a traceback would show it."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ProviderError):
            return current if current.rate_limited else None
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return None


def next_delay(config: QuotaWaitConfig, attempts: int, hint: float | None) -> float:
    """Exponential backoff that respects a provider hint, capped at the configured interval."""
    backoff = config.initial_seconds * 2 ** min(attempts, 30)
    return float(min(config.max_interval_seconds, max(hint or 0.0, backoff)))


def not_before(until: str) -> datetime | None:
    if not until:
        return None
    try:
        return datetime.fromisoformat(until)
    except ValueError:
        return None


def status_message(status: str, until: str, current: datetime | None = None) -> str:
    """Literal status text for a future quota wait; empty when none is scheduled."""
    moment = not_before(until)
    if status != "waiting" or moment is None:
        return ""
    local = moment.astimezone()
    reference = (current or datetime.now(local.tzinfo)).astimezone(local.tzinfo)
    if local <= reference:
        return ""  # an elapsed time is not a scheduled wait
    shown = local.strftime("%H:%M")
    if local.date() != reference.date():
        shown = local.strftime("%Y-%m-%d %H:%M")
    return f"Waiting for provider quota; next attempt at {shown}"
