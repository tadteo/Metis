"""Model-facing evidence presentation; durable evidence is never modified.

Only recognized evidence/report schemas are projected. Arbitrary dictionaries,
experiments and history records retain their content. Evidence passages
(abstract, excerpt, full text) are shown as bounded excerpts under a per-request
budget; complete records remain in the Store and artifacts, and every record keeps
its ID and hash so it stays citable. Limits are display policy, not a scientific
relevance filter or a replacement for the final request reservation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Iterator
from typing import Any

from .contracts import Evidence
from .privacy import redact

TITLE_CHARS = 1024
VENUE_CHARS = 512
# Passage bounds (characters). The per-request budget counts unique records once.
ABSTRACT_CHARS = 3000
EXCERPT_CHARS = 2000
FULL_TEXT_CHARS = 6000
EVIDENCE_PASSAGE_CHARS = 80000
WINDOW_CHARS = 1000
MIN_FULL_TEXT_CHARS = 1000
WINDOW_SEPARATOR = "\n[...]\n"
VIEW_VERSION = 2
_EVIDENCE_FIELDS = set(Evidence.model_fields) - {"excerpt"}
_TRANSPORT = {"record", "raw_source", "raw_response"}
_PASSAGES = ("abstract", "excerpt", "full_text")
_TERM = re.compile(r"[a-z0-9][a-z0-9-]{3,}")
_STOP = frozenset(
    "about above after again against also among based because been before being below "
    "between both could does doing during each from further have having into itself more "
    "most other over same should some such than that their them then there these they "
    "this those through under until very were what when where which while with within "
    "would your using used paper study method methods results".split()
)


def _is_evidence(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and _EVIDENCE_FIELDS <= item.keys()
        and isinstance(item["retrieval"], dict)
    )


def _terms(text: str) -> set[str]:
    return {term for term in _TERM.findall(text.lower()) if term not in _STOP}


def _evidence_records(value: Any) -> Iterator[dict[str, Any]]:
    """Top-level evidence records; transport copies inside a record are not visited."""
    if isinstance(value, list):
        for child in value:
            yield from _evidence_records(child)
    elif isinstance(value, dict):
        if _is_evidence(value):
            yield value
            return
        for child in value.values():
            yield from _evidence_records(child)


def _identity(item: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()


def _strings(value: Any, limit: int) -> list[str]:
    found: list[str] = []
    total = 0
    stack = [value]
    while stack and total < limit:
        item = stack.pop()
        if isinstance(item, str):
            found.append(item)
            total += len(item)
        elif isinstance(item, list):
            stack.extend(reversed(item))
        elif isinstance(item, dict) and not _is_evidence(item):
            stack.extend(reversed(list(item.values())))
    return found


_CITING_KEYS = frozenset({"evidence_ids", "evidence", "sources", "source_ids"})


def _cited_ids(value: Any) -> set[str]:
    """IDs listed under evidence-citing keys (claims, ideas); retrieval reports excluded."""
    found: set[str] = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict) and not _is_evidence(item):
            for key, child in item.items():
                if key == "search_reports":
                    continue
                if key in _CITING_KEYS and isinstance(child, list):
                    found.update(entry for entry in child if isinstance(entry, str))
                else:
                    stack.append(child)
    return found


def evidence_focus(
    state: dict[str, Any], context: dict[str, Any], *, limit: int = 20000
) -> tuple[str, set[str]]:
    """Stage focus text and priority evidence IDs for passage selection.

    Focus uses the task title/objective, the ideas under consideration and
    non-evidence stage context. Priority IDs are evidence linked to those ideas or
    named in the stage context (for example cited by claims under audit).
    """
    wanted = {str(item) for item in context.get("active_seed_ids") or []}
    if state.get("selected_idea"):
        wanted.add(str(state["selected_idea"]))
    ideas = [
        idea
        for idea in state.get("ideas") or []
        if isinstance(idea, dict)
        and (idea.get("id") in wanted or idea.get("status") == "pending_novelty")
    ]
    parts = [str(state.get("title", "")), str(state.get("objective", ""))]
    priority: set[str] = set()
    for idea in ideas:
        parts.extend(str(idea.get(key, "")) for key in ("title", "hypothesis", "rationale"))
        priority.update(str(item) for item in idea.get("evidence") or [])
    parts.extend(_strings(context, limit))
    priority.update(_cited_ids(context))
    return "\n".join(parts)[:limit], priority


def _fit(lengths: list[int], budget: int) -> int:
    """Largest common cap so that sum(min(length, cap)) <= budget."""
    if sum(lengths) <= budget:
        return max(lengths, default=0)
    low, high = 0, max(lengths)
    while low < high:
        middle = (low + high + 1) // 2
        if sum(min(length, middle) for length in lengths) <= budget:
            low = middle
        else:
            high = middle - 1
    return low


def _allocate(
    records: list[dict[str, Any]], focus: set[str], priority: Collection[str], budget: int
) -> dict[str, dict[str, int]]:
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        unique.setdefault(_identity(record), record)
    shown: dict[str, dict[str, int]] = {}
    short: list[tuple[str, str, int]] = []
    for key, record in unique.items():
        shown[key] = {}
        for field, cap in (("abstract", ABSTRACT_CHARS), ("excerpt", EXCERPT_CHARS)):
            text = record.get(field)
            if field == "excerpt" and text == record.get("abstract"):
                continue
            if isinstance(text, str) and text:
                short.append((key, field, min(len(text), cap)))
    # Evidence under assessment keeps full-text room even when abstracts are many.
    reserved = min(
        budget // 2,
        sum(
            min(len(record["full_text"]), FULL_TEXT_CHARS)
            for record in unique.values()
            if record.get("id") in priority
            and isinstance(record.get("full_text"), str)
            and record["full_text"]
        ),
    )
    cap = _fit([length for *_, length in short], budget - reserved)
    for key, field, length in short:
        shown[key][field] = min(length, cap)
    remaining = budget - sum(sum(fields.values()) for fields in shown.values())

    def rank(entry: tuple[int, tuple[str, dict[str, Any]]]) -> tuple[int, int, int]:
        position, (_, record) = entry
        summary = f"{record.get('title', '')} {record.get('abstract', '')}"
        body = record.get("full_text")
        body = body if isinstance(body, str) else ""
        # Distinct focus terms; bibliographic summary matches count twice.
        overlap = 2 * len(focus & _terms(summary)) + len(focus & _terms(body))
        return (record.get("id") not in priority, -overlap, position)

    for _, (key, record) in sorted(enumerate(unique.items()), key=rank):
        text = record.get("full_text")
        if not isinstance(text, str) or not text:
            continue
        allowed = min(len(text), FULL_TEXT_CHARS, remaining)
        if allowed < min(len(text), MIN_FULL_TEXT_CHARS):
            allowed = 0
        shown[key]["full_text"] = allowed
        remaining -= allowed
    return shown


def _windows(text: str, limit: int, focus: set[str]) -> tuple[str, list[list[int]]]:
    """Focus-ranked windows in document order; leading text when nothing matches."""
    if limit <= 0:
        return "", []
    if len(text) <= limit:
        return text, [[0, len(text)]]
    spans = [
        (start, min(start + WINDOW_CHARS, len(text))) for start in range(0, len(text), WINDOW_CHARS)
    ]
    scores = []
    for index, (start, end) in enumerate(spans):
        words = _TERM.findall(text[start:end].lower())
        scores.append((-sum(word in focus for word in words), index))
    chosen: list[int] = []
    used = 0
    if focus and scores and min(scores)[0] < 0:
        for score, index in sorted(scores):
            if score == 0:
                break
            start, end = spans[index]
            extra = (end - start) + (len(WINDOW_SEPARATOR) if chosen else 0)
            if used + extra > limit:
                continue
            chosen.append(index)
            used += extra
    if not chosen:
        return text[:limit], [[0, limit]]
    chosen.sort()
    merged: list[list[int]] = []
    for index in chosen:
        start, end = spans[index]
        if merged and merged[-1][1] == start:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return WINDOW_SEPARATOR.join(text[start:end] for start, end in merged), merged


def retrieval_model_view(
    value: Any,
    *,
    deduplicate: bool = False,
    focus: str = "",
    priority_ids: Collection[str] = (),
    passage_budget: int = EVIDENCE_PASSAGE_CHARS,
) -> Any:
    """Return a non-mutating, idempotent projection; optional exact-copy references.

    Evidence passages are bounded per record and across the request: abstracts and
    separate excerpts first, then full-text windows for ``priority_ids`` and records
    most related to ``focus``. Each shortened passage is listed in
    ``model_view.omissions`` with its original size, hash and shown windows.
    References point to the first inline occurrence in this same JSON document.
    Distinct versions or contradictory passages never collapse merely by ID.
    """
    seen: dict[str, str] = {}
    focus_terms = _terms(focus)
    allocation = _allocate(
        list(_evidence_records(value)), focus_terms, set(priority_ids), passage_budget
    )

    def visit(item: Any, pointer: str) -> Any:
        if isinstance(item, list):
            return [visit(child, f"{pointer}/{index}") for index, child in enumerate(item)]
        if not isinstance(item, dict):
            return item
        viewed = {
            key: visit(child, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1"))
            for key, child in item.items()
        }
        if _is_evidence(item):
            viewed["retrieval"] = {
                key: child for key, child in viewed["retrieval"].items() if key not in _TRANSPORT
            }
            if item.get("excerpt") == item["abstract"]:
                viewed.pop("excerpt", None)
            omissions = dict(viewed.get("model_view", {}).get("omissions", {}))
            limits = allocation.get(_identity(item), {})
            for field in _PASSAGES:
                text = viewed.get(field)
                limit = limits.get(field, 0)
                if not isinstance(text, str) or len(text) <= limit:
                    continue
                if field == "full_text":
                    shown, windows = _windows(text, limit, focus_terms)
                else:
                    shown, windows = text[:limit], [[0, limit]] if limit else []
                viewed[field] = shown
                previous = omissions.get(field)
                omissions[field] = (
                    {**previous, "shown_chars": len(shown), "windows": None, "reprojected": True}
                    if isinstance(previous, dict) and "original_chars" in previous
                    else {
                        "original_chars": len(text),
                        "shown_chars": len(shown),
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "reason": "bounded_evidence_passage",
                        "windows": windows,
                    }
                )
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
                viewed["model_view"] = {"version": VIEW_VERSION, "omissions": omissions}
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
        if _is_evidence(item):
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


def evidence_view_summary(
    projected: Any, *, passage_budget: int = EVIDENCE_PASSAGE_CHARS
) -> dict[str, Any]:
    """Provenance for one request: included evidence IDs and passage truncation."""
    ids: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    stack = [projected]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(reversed(item))
        elif isinstance(item, dict):
            if "evidence_ref" in item and "context_pointer" in item:
                ids.append(str(item["evidence_ref"]))
            elif _is_evidence(item):
                ids.append(str(item["id"]))
                records.setdefault(_identity(item), item)
            else:
                stack.extend(reversed(list(item.values())))
    shown = original = 0
    truncated: list[dict[str, Any]] = []
    for record in records.values():
        omissions = record.get("model_view", {}).get("omissions", {})
        entry: dict[str, Any] = {
            "id": str(record["id"]),
            "content_hash": str(record.get("content_hash", "")),
        }
        for field in _PASSAGES:
            text = record.get(field)
            length = len(text) if isinstance(text, str) else 0
            omitted = omissions.get(field)
            shown += length
            if isinstance(omitted, dict):
                original += int(omitted.get("original_chars", length))
                entry[field] = {
                    "original_chars": int(omitted.get("original_chars", length)),
                    "shown_chars": length,
                }
            else:
                original += length
        if len(entry) > 2:
            truncated.append(entry)
    return {
        "version": VIEW_VERSION,
        "evidence_ids": list(dict.fromkeys(ids)),
        "records": len(records),
        "passage_budget_chars": passage_budget,
        "passage_chars_shown": shown,
        "passage_chars_original": original,
        "truncated": truncated,
    }


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
