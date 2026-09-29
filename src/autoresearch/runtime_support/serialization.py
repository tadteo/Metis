"""Stable identities for JSON-compatible runtime records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def content_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
