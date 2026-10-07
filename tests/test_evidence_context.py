"""Adverse model-context tests; all source data is synthetic."""

import copy
import hashlib
import json

from autoresearch.contracts import Evidence
from autoresearch.evidence_context import (
    EVIDENCE_PASSAGE_CHARS,
    FULL_TEXT_CHARS,
    evidence_focus,
    evidence_view_summary,
)
from autoresearch.review import retrieval_model_view


def paper():
    return Evidence(
        id="public-fixture",
        title="issue contents " * 12000,
        url="https://example.org/paper",
        content_hash="a" * 64,
        abstract="A contradictory result that must remain inspectable.",
        retrieval={"record": {"body": "transport" * 20000}, "venue": "venue" * 1000},
    ).model_dump()


def test_metadata_is_bounded_without_losing_passages_or_mutating_evidence():
    raw = paper()
    before = copy.deepcopy(raw)
    viewed = retrieval_model_view(raw)
    assert len(json.dumps(viewed)) < 6000
    assert viewed["abstract"] == raw["abstract"]
    assert viewed["content_hash"] == raw["content_hash"]
    assert viewed["model_view"]["omissions"]["title"]["original_chars"] == len(raw["title"])
    assert raw == before
    assert retrieval_model_view(viewed) == viewed


def test_references_resolve_only_to_retained_exact_copies():
    raw = paper()
    # Transport may contain a complete record that is later removed.
    raw["retrieval"]["record"] = paper()
    conflict = {**raw, "abstract": "Opposite conclusion with the same reported identifier."}
    viewed = retrieval_model_view(
        {"state": {"evidence": [raw]}, "retrieved": [raw, conflict]}, deduplicate=True
    )
    assert viewed["retrieved"][0]["context_pointer"] == "/state/evidence/0"
    assert viewed["retrieved"][0]["evidence_ref"] == raw["id"]
    assert viewed["retrieved"][1]["abstract"] == conflict["abstract"]
    assert "record" not in viewed["state"]["evidence"][0]["retrieval"]
    assert retrieval_model_view(viewed, deduplicate=True) == viewed


def test_projection_preserves_arbitrary_science_and_bounds_full_passages():
    scientific = {"title": "t" * 20000, "raw_response": "negative", "record": [1, 2]}
    raw = paper()
    raw["full_text"] = "negative measured result " * 10000
    raw["retrieval"]["raw_source"] = scientific
    before = copy.deepcopy(raw)
    viewed = retrieval_model_view({"experiment": scientific, "source": raw})
    assert viewed["experiment"] == scientific
    assert raw == before
    shown = viewed["source"]["full_text"]
    assert 0 < len(shown) <= FULL_TEXT_CHARS
    omitted = viewed["source"]["model_view"]["omissions"]["full_text"]
    assert omitted["original_chars"] == len(raw["full_text"])
    assert omitted["shown_chars"] == len(shown)
    assert omitted["sha256"] == hashlib.sha256(raw["full_text"].encode()).hexdigest()
    assert omitted["reason"] == "bounded_evidence_passage"
    for start, end in omitted["windows"]:
        assert raw["full_text"][start:end] in shown
    assert retrieval_model_view(viewed) == viewed


def live_shape(count=39, full_text_chars=34000):
    """Synthetic records shaped like the 2026-10-07 novelty request (no private text)."""
    records = []
    for index in range(count):
        body = (f"Section {index}: synthetic calibration observation and measured drift. ") * (
            full_text_chars // 70
        )
        records.append(
            Evidence(
                id=f"synthetic-{index}",
                title=f"Synthetic fixture paper {index}",
                url=f"https://example.org/{index}",
                content_hash=f"{index:064x}",
                abstract=f"Synthetic abstract {index}. " * 50,
                full_text=body[:full_text_chars],
                retrieval={"venue": "Fixture venue", "full_text_status": "retrieved"},
            ).model_dump()
        )
    return records


def test_live_shape_passages_fit_the_request_budget_and_stay_citable():
    records = live_shape()
    raw_chars = len(json.dumps(records))
    assert raw_chars > 1_300_000
    viewed = retrieval_model_view({"state": {"evidence": records}}, deduplicate=True)
    summary = evidence_view_summary(viewed)
    assert summary["passage_chars_shown"] <= EVIDENCE_PASSAGE_CHARS
    assert summary["passage_chars_original"] == sum(
        len(r["abstract"]) + len(r["full_text"]) for r in records
    )
    assert summary["evidence_ids"] == [r["id"] for r in records]
    assert len(summary["truncated"]) == len(records)
    assert len(json.dumps(viewed)) < 200_000
    for record, shown in zip(records, viewed["state"]["evidence"], strict=True):
        assert shown["id"] == record["id"] and shown["content_hash"] == record["content_hash"]
        assert shown["abstract"] == record["abstract"]


def test_focus_and_priority_choose_relevant_full_text():
    records = live_shape(count=30)
    target = records[17]
    target["full_text"] = (
        "Unrelated preamble text. " * 800
        + "Quasicrystal annealing reverses the reported effect. "
        + "Unrelated closing text. " * 800
    )
    focus, priority = evidence_focus(
        {
            "title": "Quasicrystal annealing",
            "objective": "Test annealing",
            "ideas": [{"id": "idea", "title": "t", "hypothesis": "h", "evidence": ["synthetic-3"]}],
        },
        {"active_seed_ids": ["idea"]},
    )
    assert "synthetic-3" in priority
    viewed = retrieval_model_view(records, focus=focus, priority_ids=priority)
    assert "reverses the reported effect" in viewed[17]["full_text"]
    assert viewed[3]["full_text"]  # linked to the idea under assessment
    assert not viewed[29]["full_text"]  # budget exhausted for unrelated records
    assert viewed[29]["model_view"]["omissions"]["full_text"]["shown_chars"] == 0


def test_oversized_abstracts_share_the_budget_evenly():
    records = live_shape(count=5, full_text_chars=0)
    for record in records:
        record["abstract"] = "a" * 50000
    viewed = retrieval_model_view(records, passage_budget=10000)
    assert [len(r["abstract"]) for r in viewed] == [2000] * 5
    assert viewed[0]["model_view"]["omissions"]["abstract"]["original_chars"] == 50000


def test_history_counts_projected_content_before_selection():
    from autoresearch.evidence_context import recent_history

    steps = [
        {"action": [{"tool": "read", "path": "model.py"}], "observation": "important code"},
        {"action": [{"tool": "discover"}], "observation": {"evidence": [paper()]}},
    ]
    before = copy.deepcopy(steps)
    viewed = recent_history(steps, 10000)
    assert len(viewed) == 2
    assert viewed[0] == steps[0]
    assert len(json.dumps(viewed)) <= 10000
    assert steps == before


def test_priority_evidence_keeps_full_text_when_abstracts_fill_the_budget():
    records = live_shape(count=40, full_text_chars=20000)
    for record in records:
        record["abstract"] = "b" * 2500
    viewed = retrieval_model_view(records, priority_ids={"synthetic-7", "synthetic-30"})
    assert len(viewed[7]["full_text"]) == FULL_TEXT_CHARS
    assert len(viewed[30]["full_text"]) == FULL_TEXT_CHARS
    summary = evidence_view_summary(viewed)
    assert summary["passage_chars_shown"] <= EVIDENCE_PASSAGE_CHARS
    assert retrieval_model_view(viewed, priority_ids={"synthetic-7", "synthetic-30"}) == viewed


def test_priority_comes_from_citing_keys_not_arbitrary_strings():
    _, priority = evidence_focus(
        {"title": "t", "objective": "o"},
        {
            "claim_report": {"claims": [{"text": "x", "evidence_ids": ["cited"]}]},
            "task": "short instruction",
            "search_reports": [{"evidence_ids": ["retrieved-only"]}],
        },
    )
    assert priority == {"cited"}


def test_reprojection_and_duplicate_ids_keep_provenance_distinct():
    first = live_shape(count=1, full_text_chars=20000)[0]
    second = {**first, "content_hash": "f" * 64, "full_text": "other " * 4000}
    summary = evidence_view_summary(retrieval_model_view([first, second]))
    assert [item["content_hash"] for item in summary["truncated"]] == ["0" * 64, "f" * 64]
    viewed = retrieval_model_view(first)
    again = retrieval_model_view(viewed, passage_budget=1500)
    omitted = again["model_view"]["omissions"]["full_text"]
    assert omitted["original_chars"] == len(first["full_text"]) and omitted["windows"] is None
    assert omitted["reprojected"] and omitted["shown_chars"] == len(again["full_text"])
