"""On-demand Markdown projection of saved reports; never changes research records."""

from typing import Any

from markdown_it import MarkdownIt


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _literal(value: Any) -> str:
    text = str(value).replace("\n", " ")
    return "".join("\\" + char if char in "\\`*_{}[]<>()#!|" else char for char in text)


def _evidence(value: Any, depth: int = 3) -> str:
    """Use sections for narrative, lists for records, and preserve every field."""
    heading = "#" * min(depth, 6)
    if isinstance(value, dict):
        parts, sections = [], []
        for key, item in value.items():
            if isinstance(item, (dict, list)) or (
                isinstance(item, str)
                and (
                    len(item) > 120
                    or "\n" in item
                    or key in {"summary", "feedback", "reason", "failure", "note", "title"}
                )
            ):
                sections.append(
                    f"{heading} {_literal(_label(key))}\n\n{_evidence(item, depth + 1)}"
                )
            else:
                parts.append(f"- **{_literal(_label(key))}:** {_literal(item)}")
        return "\n\n".join(parts + sections)
    if isinstance(value, list):
        return (
            "\n\n".join(
                f"{heading} Record {index}\n\n{_evidence(item, depth + 1)}"
                if isinstance(item, dict)
                else "- " + _evidence(item, depth + 1).replace("\n", "\n  ")
                for index, item in enumerate(value, 1)
            )
            or "None recorded."
        )
    return str(value)


def report_document(report: dict[str, Any]) -> dict[str, Any]:
    data = report["payload"]
    parts = [
        f"# {_literal(_label(data['stage']))} — stage report",
        "\n".join(
            [
                f"- **Checkpoint:** {data['checkpoint']}",
                f"- **Round:** {data['round']}",
                f"- **Status:** {_literal(data['status'])}",
                f"- **Recorded:** {_literal(report['timestamp'])}",
                f"- **Checkpoint result:** {_literal(_label(data['kind']))}",
                f"- **Candidate:** {_literal(data.get('idea') or 'None recorded')}",
                f"- **Source event:** {data['event_seq']}",
            ]
        ),
    ]
    if data.get("synthetic"):
        parts.append("> Synthetic demonstration — not research evidence.")
    parts.append("## Decision and explanation")
    explanations = list(
        dict.fromkeys(
            str(data[key]) for key in ("outcome", "feedback", "error", "reason") if data.get(key)
        )
    )
    parts.extend(
        explanations
        or [
            "No new overall explanation recorded. Inspect the observations for individual decisions."
        ]
    )
    parts.append("## Observations and evidence")
    changes = data.get("changes", {})
    for key, value in changes.items():
        parts.append(f"### {_literal(_label(key))}\n\n{_evidence(value, 4)}")
    if not changes:
        parts.append("No new observations recorded at this checkpoint.")
    parts.append(
        f"## What happens next\n\n{_literal(_label(data['next_stage']))} · {_literal(data['status'])}."
    )
    markdown = "\n\n".join(parts) + "\n"
    parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    return {
        "markdown": markdown,
        "tokens": [token.as_dict(as_upstream=False) for token in parser.parse(markdown)],
    }
