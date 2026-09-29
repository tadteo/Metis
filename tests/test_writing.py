from typing import Any

from test_review import FixtureLiterature

from autoresearch.contracts import AgentOutput, RunState
from autoresearch.writing import compose_manuscript


def test_writer_retains_section_work_and_reflection_feedback():
    roles = []

    def call(role: str, context: dict[str, Any]) -> AgentOutput:
        roles.append(role)
        if role == "writing_reflection":
            return AgentOutput(summary="Audit", decision="refine", feedback="Fix unsupported claim")
        if role in {"writing_section", "draft", "writing_repair"}:
            return AgentOutput(
                summary="Draft",
                manuscript=context.get("section", "Full evidence-grounded manuscript"),
            )
        return AgentOutput(summary="Outline and literature")

    draft, refs = compose_manuscript(
        RunState(id="fixture", title="Study", objective="Research"), call, FixtureLiterature(), 2, 2
    )
    assert roles.count("writing_section") == 8
    assert roles.count("writing_reflection") == 2
    assert roles.count("writing_repair") == 2
    assert "writing_literature" in roles
    assert "writing_figure_plan" in roles
    assert draft.manuscript
    assert refs
