"""Human-readable terminal projections; complete receipts remain separately inspectable."""

from __future__ import annotations

from typing import Any


def human(value: str) -> str:
    return value.replace("_", " ").capitalize()


def experiment_reading(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    lines = [str(value.get("id", "Experiment")), human(str(value.get("status", "Recorded")))]
    metrics = value.get("metrics", {})
    if metrics:
        lines += ["", "Measured results", *[f"{key}   {score}" for key, score in metrics.items()]]
    else:
        lines += ["", "No measured results recorded."]
    for label, key in (
        ("Notes", "note"),
        ("Output", "stdout"),
        ("Diagnostics", "stderr"),
        ("Error", "error"),
    ):
        if value.get(key):
            text = str(value[key])
            lines += [
                "",
                label,
                text[:2000]
                + ("\n… Complete text is in the receipt below." if len(text) > 2000 else ""),
            ]
    return "\n".join(lines)


def event_reading(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    lines = [
        human(str(value.get("kind", "Event"))),
        str(value.get("timestamp", "")),
        human(str(value.get("stage", ""))),
    ]
    payload = value.get("payload", {})
    if isinstance(payload, dict):
        for key in ("summary", "message", "decision", "feedback", "error", "reason"):
            if payload.get(key):
                text = str(payload[key])
                lines += [
                    "",
                    human(key),
                    text[:2000]
                    + ("\n… Complete text is in the trace below." if len(text) > 2000 else ""),
                ]
    lines += ["", "The complete event below preserves the recorded details and available trace."]
    return "\n".join(lines)
