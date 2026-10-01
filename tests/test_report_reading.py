"""Readable public synthetic reports retain content without executable markup."""

from copy import deepcopy

from autoresearch.report_reading import report_document


def fixture():
    return {
        "timestamp": "2026-10-01T12:00:00Z",
        "payload": {
            "stage": "verify_limitations",
            "checkpoint": 4,
            "round": 0,
            "status": "blocked",
            "kind": "stage_error",
            "event_seq": 20,
            "synthetic": True,
            "next_stage": "verify_limitations",
            "feedback": "## Findings\n\n**Measured evidence** is missing.\n\n- First reason\n- Second reason\n\n| Measure | Result |\n| --- | --- |\n| score | 0.7 |\n\n```python\nassert score > 0\n```",
            "error": "<script>alert(1)</script>",
            "changes": {
                "memory": [{"decision": "reject", "feedback": "**Revise** the experiment."}]
            },
        },
    }


def flatten(tokens):
    for token in tokens:
        yield token
        yield from flatten(token.get("children") or [])


def test_markdown_report_formats_existing_evidence_without_mutation():
    report = fixture()
    original = deepcopy(report)
    result = report_document(report)
    tokens = list(flatten(result["tokens"]))
    assert {"heading_open", "bullet_list_open", "strong_open", "table_open", "fence"} <= {
        t["type"] for t in tokens
    }
    assert "Synthetic demonstration" in result["markdown"]
    assert "**Revise** the experiment." in result["markdown"]
    assert "reject" in result["markdown"]
    assert any(t["type"] == "text" and "<script>" in t["content"] for t in tokens)
    assert not any(t["type"].startswith("html_") for t in tokens)
    assert report == original


def test_unsafe_links_and_metadata_stay_literal():
    report = fixture()
    report["payload"]["idea"] = "<img src=x> [unsafe](javascript:alert(1))"
    report["payload"]["feedback"] = (
        "[unsafe](javascript:alert(1))\n\n[reference](https://example.org/paper)\n\n![external](https://example.org/tracker.png)"
    )
    tokens = list(flatten(report_document(report)["tokens"]))
    links = [t["attrs"]["href"] for t in tokens if t["type"] == "link_open"]
    assert links == ["https://example.org/paper"]
    assert not any(t["type"].startswith("html_") for t in tokens)


def test_scalar_metadata_does_not_appear_inside_previous_nested_section():
    report = fixture()
    report["payload"]["changes"] = {
        "memory": [{"metrics": {"score": 0.7}, "source": "Original source"}]
    }
    markdown = report_document(report)["markdown"]
    assert markdown.index("Original source") < markdown.index("##### Metrics")
