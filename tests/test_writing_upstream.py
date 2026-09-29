"""Opt-in no-network smoke against the actual pinned official source/runtime.

PAPER_ORCHESTRA_TEST_CHECKOUT=/path/to/pinned/source pytest tests/test_writing_upstream.py
Install the hash-locked writer runtime into the test environment first.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from autoresearch.paper_orchestra import PaperOrchestraConfig, verify_checkout
from autoresearch.paper_orchestra_worker import CallJournal, Transports


@pytest.mark.skipif(
    not os.getenv("PAPER_ORCHESTRA_TEST_CHECKOUT"),
    reason="requires pinned upstream checkout and runtime",
)
def test_official_agents_import_and_outline_uses_routed_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream = Path(os.environ["PAPER_ORCHESTRA_TEST_CHECKOUT"])
    verify_checkout(upstream)
    monkeypatch.syspath_prepend(str(upstream))
    options = PaperOrchestraConfig().model_dump(mode="json")
    options["compatible_models"]["test-model"] = {}
    transports = Transports(CallJournal(tmp_path, options))
    # Restore SDK factories so this opt-in test has no side effects on other tests.
    genai = importlib.import_module("google.genai")
    openai = importlib.import_module("openai")
    monkeypatch.setattr(genai, "Client", genai.Client)
    monkeypatch.setattr(openai, "OpenAI", openai.OpenAI)
    monkeypatch.setenv("GEMINI_API_KEY", "test-unused")
    monkeypatch.setenv("OPENAI_API_KEY", "test-unused")
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    transports.install()
    for name in (
        "outline_agent",
        "literature_review_agent",
        "section_writing_agent",
        "content_refinement_agent",
        "plotting_agent",
    ):
        importlib.import_module("methods.agents." + name)
    calls: list[Any] = []

    def complete(alias: str, messages: list[Any], temperature: Any = None) -> Any:
        calls.append(messages)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop", message=SimpleNamespace(content='{"section_plan": []}')
                )
            ]
        )

    monkeypatch.setattr(transports, "_compatible", complete)
    for name in ("idea.md", "log.md", "template.tex", "guidelines.md"):
        (tmp_path / name).write_text("Measured research input")
    cls = importlib.import_module("methods.agents.outline_agent").OutlineAgent
    cls(model_name="test-model").run(
        idea_file=str(tmp_path / "idea.md"),
        experimental_log_file=str(tmp_path / "log.md"),
        latex_template_file=str(tmp_path / "template.tex"),
        conference_guidelines_file=str(tmp_path / "guidelines.md"),
        output_filepath=str(tmp_path / "outline.json"),
    )
    assert json.loads((tmp_path / "outline.json").read_text()) == {"section_plan": []}
    assert len(calls) == 1
    assert "Measured research input" in json.dumps(calls)
