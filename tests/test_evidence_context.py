"""Adverse model-context tests; all source data is synthetic."""

import copy
import json

from autoresearch.contracts import Evidence
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


def test_projection_preserves_arbitrary_science_and_full_passages():
    scientific = {"title": "t" * 20000, "raw_response": "negative", "record": [1, 2]}
    raw = paper()
    raw["full_text"] = "negative measured result " * 10000
    raw["retrieval"]["raw_source"] = scientific
    viewed = retrieval_model_view({"experiment": scientific, "source": raw})
    assert viewed["experiment"] == scientific
    assert viewed["source"]["full_text"] == raw["full_text"]


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
