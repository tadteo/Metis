"""Model-facing bibliographic presentation; durable evidence is never modified.

Only recognized evidence/report schemas are projected. Scientific passages and
arbitrary dictionaries retain their content. Limits are display policy, not a
scientific relevance filter or a replacement for the final request reservation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import Evidence
from .privacy import redact

TITLE_CHARS = 1024
VENUE_CHARS = 512
_EVIDENCE_FIELDS = set(Evidence.model_fields) - {"excerpt"}


def retrieval_model_view(value: Any, *, deduplicate: bool = False) -> Any:
    """Return a non-mutating, idempotent projection; optional exact-copy references.

    References point to the first inline occurrence in this same JSON document.
    Distinct versions or contradictory passages never collapse merely by ID.
    """
    seen: dict[str, str] = {}

    def visit(item: Any, pointer: str) -> Any:
        if isinstance(item, list):
            return [visit(child, f"{pointer}/{index}") for index, child in enumerate(item)]
        if not isinstance(item, dict):
            return item
        viewed = {
            key: visit(child, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1"))
            for key, child in item.items()
        }
        if _EVIDENCE_FIELDS <= item.keys() and isinstance(item["retrieval"], dict):
            viewed["retrieval"] = {
                key: child
                for key, child in viewed["retrieval"].items()
                if key not in {"record", "raw_source", "raw_response"}
            }
            if item.get("excerpt") == item["abstract"]:
                viewed.pop("excerpt", None)
            omissions = dict(viewed.get("model_view", {}).get("omissions", {}))
            for container, key, limit, name in (
                (viewed, "title", TITLE_CHARS, "title"),
                (viewed["retrieval"], "venue", VENUE_CHARS, "retrieval.venue"),
            ):
                text = container.get(key)
                if isinstance(text, str) and len(text) > limit:
                    container[key] = text[:limit]
                    omissions[name] = {
                        "original_chars": len(text),
                        "shown_chars": limit,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "reason": "oversized_bibliographic_metadata",
                    }
            if omissions:
                viewed["model_view"] = {"version": 1, "omissions": omissions}
        report_fields = {
            "query",
            "cutoff",
            "retrieved_at",
            "evidence_ids",
            "providers",
            "limitations",
            "exhaustive",
        }
        if report_fields <= item.keys() and isinstance(item["providers"], list):
            viewed["providers"] = [
                {key: child for key, child in provider.items() if key != "raw_response"}
                if isinstance(provider, dict) and {"provider", "status"} <= provider.keys()
                else provider
                for provider in viewed["providers"]
            ]
        return viewed

    projected = visit(value, "")
    if not deduplicate:
        return projected

    def reference(item: Any, pointer: str) -> Any:
        if isinstance(item, list):
            return [reference(child, f"{pointer}/{index}") for index, child in enumerate(item)]
        if not isinstance(item, dict):
            return item
        if _EVIDENCE_FIELDS <= item.keys() and isinstance(item["retrieval"], dict):
            identity = json.dumps(item, sort_keys=True)
            if identity in seen:
                return {
                    "evidence_ref": item["id"],
                    "content_hash": item["content_hash"],
                    "context_pointer": seen[identity],
                }
            seen[identity] = pointer
        return {
            key: reference(child, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1"))
            for key, child in item.items()
        }

    return reference(projected, "")


def recent_history(
    steps: list[dict[str, Any]], limit: int, *, redact_patterns: list[str] | None = None
) -> list[dict[str, Any]]:
    """Select already-projected history; oversized entries remain explicitly indexed."""
    recent: list[dict[str, Any]] = []
    for index in range(len(steps) - 1, -1, -1):
        item = retrieval_model_view(redact(steps[index], redact_patterns))
        if len(json.dumps([item])) > limit:
            raw = json.dumps(steps[index])
            item = {
                "history_step": index,
                "observation_omitted": True,
                "original_chars": len(raw),
                "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "history_request": {
                    "tool": "history",
                    "offset": index,
                    "limit": 1,
                    "start_char": 0,
                },
            }
        candidate = [item, *recent]
        if len(json.dumps(candidate)) > limit:
            break
        recent = candidate
    return recent
