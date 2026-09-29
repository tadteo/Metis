"""Defense-in-depth redaction, not an assurance that arbitrary prose is anonymized."""

from __future__ import annotations

import os
import re
from typing import Any

_SECRET_KEY = re.compile(r"(?i)(api[_-]?key|authorization|password|secret|access[_-]?token)")
_TOKEN = re.compile(r"\b(?:sk-|xai-|sk_or_|ghp_|github_pat_)[A-Za-z0-9_-]{12,}\b")
_HOME = re.compile(r"(?:/Users/|/home/)[^/\s\"']+")


def redact(value: Any, patterns: list[str] | None = None, *, preserve_paths: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]"
            if _SECRET_KEY.search(str(k)) and not str(k).endswith("_env")
            else redact(v, patterns, preserve_paths=preserve_paths)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, patterns, preserve_paths=preserve_paths) for v in value]
    if not isinstance(value, str):
        return value
    for key, secret in os.environ.items():
        if key.endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")) and len(secret) >= 8:
            value = value.replace(secret, "[REDACTED]")
    value = _TOKEN.sub("[REDACTED]", value)
    value = re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [REDACTED]", value)
    if not preserve_paths:
        value = _HOME.sub("[HOME]", value)
    for pattern in patterns or []:
        value = re.sub(pattern, "[REDACTED]", value)
    return value
