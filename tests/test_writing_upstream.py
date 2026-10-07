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


@pytest.mark.skipif(
    not os.getenv("PAPER_ORCHESTRA_TEST_CHECKOUT"),
    reason="requires pinned upstream checkout and runtime",
)
def test_metis_retrieval_feeds_real_official_literature_downstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D04: only discovery is substituted; real S2 matching, BibTeX and synthesis run."""
    from autoresearch.config import LiteratureConfig, ResearchConfig
    from autoresearch.literature import Literature, ProviderResult, _evidence
    from autoresearch.paper_orchestra import PaperOrchestraError, resolve_writer_config
    from autoresearch.paper_orchestra_worker import (
        DISCOVERY_LOG,
        MetisLiteratureDiscovery,
        StageJournal,
        discovery_agent,
        export_evidence,
        instrument_search,
    )

    upstream = Path(os.environ["PAPER_ORCHESTRA_TEST_CHECKOUT"])
    verify_checkout(upstream)
    monkeypatch.syspath_prepend(str(upstream))
    config = ResearchConfig(
        paper_orchestra=PaperOrchestraConfig(
            literature_discovery="metis_retrieval",
            use_plotting=False,
            literature_model_name="test-model",
        ),
        literature=LiteratureConfig(providers=["semantic_scholar"], full_text=False),
    )
    options = resolve_writer_config(config)
    options.update(research_cutoff="2026-09")
    options["compatible_models"]["test-model"] = {}
    journal = CallJournal(tmp_path, options)
    transports = Transports(journal)
    genai = importlib.import_module("google.genai")
    openai = importlib.import_module("openai")
    requests: Any = importlib.import_module("requests")
    monkeypatch.setattr(genai, "Client", genai.Client)
    monkeypatch.setattr(openai, "OpenAI", openai.OpenAI)
    monkeypatch.setenv("GEMINI_API_KEY", "test-unused")
    monkeypatch.setenv("OPENAI_API_KEY", "test-unused")
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    s2_queries: list[str] = []

    def s2(url: str, **kwargs: Any) -> Any:
        query = kwargs["params"]["query"]
        s2_queries.append(query)
        paper = {
            "paperId": "p" + str(len(s2_queries)),
            "title": query,
            "authors": [{"name": "Ada Lovelace"}],
            "venue": "ICLR",
            "year": 2024,
            "abstract": "Synthetic abstract for " + query,
            "citationCount": 3,
            "publicationDate": "2024-05-01",
            "externalIds": {"DOI": "10.0/" + str(len(s2_queries))},
        }
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"data": [paper]}).encode()
        return response

    monkeypatch.setattr(requests, "get", s2)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    instrument_search(tmp_path)
    transports.install()
    importlib.import_module("utils.gemini_utils").genai_client = genai.Client()
    synthesis: list[Any] = []

    def complete(alias: str, messages: list[Any], temperature: Any = None) -> Any:
        synthesis.append(messages)
        text = "```latex\n\\section{Introduction} \\cite{Lovelace2024SparseAttention}\n```"
        return SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=text))]
        )

    monkeypatch.setattr(transports, "_compatible", complete)
    types = importlib.import_module("google.genai.types")
    with pytest.raises(PaperOrchestraError, match="grounding is disabled"):
        transports.gemini(
            model="gemini-3-flash-preview",
            contents=["search"],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )

    class Provider:
        name = "semantic_scholar"

        def search(self, query: str, count: int, cutoff: str) -> ProviderResult:
            paper = _evidence(
                {
                    "title": "Sparse Attention Survey",
                    "url": "https://example.org/sparse",
                    "abstract": "Synthetic",
                    "provider": self.name,
                    "published_at": "2024-05-01",
                }
            )
            return ProviderResult([paper], 1, "{}", "https://fake.invalid", {"query": query})

    adapter = MetisLiteratureDiscovery(
        tmp_path, options, journal, lambda: Literature(config, providers=[Provider()])
    )
    cls = discovery_agent(
        importlib.import_module("methods.agents.literature_review_agent").HybridLiteratureAgent,
        adapter,
    )
    for name in ("idea.md", "log.md", "template.tex", "guidelines.md"):
        (tmp_path / name).write_text("Measured research input")
    outline = tmp_path / "outline.json"
    outline.write_text(
        json.dumps(
            {
                "intro_related_work_plan": {
                    "introduction_strategy": {"search_directions": ["sparse attention"]},
                    "related_work_strategy": {"subsections": []},
                },
                "section_plan": [],
            }
        )
    )
    literature_dir = tmp_path / "literature"

    def literature() -> None:
        cls(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "log.md"),
            latex_template_path=str(tmp_path / "template.tex"),
            conference_guidelines_path=str(tmp_path / "guidelines.md"),
            output_dir=str(literature_dir),
            model_name="test-model",
            max_workers=1,
        ).run(outline_path=str(outline), cutoff_date="2026-09")
        adapter.finish()

    StageJournal(tmp_path).run("literature", literature, [literature_dir / "citation_map.json"])
    citations = json.loads((literature_dir / "citation_map.json").read_text())
    assert [c["title"] for c in citations.values()] == ["Sparse Attention Survey"]
    assert "Lovelace2024SparseAttention" in (literature_dir / "references.bib").read_text()
    assert s2_queries == ["Sparse Attention Survey"]  # Official S2 title verification ran.
    assert len(synthesis) == 1 and "Sparse Attention Survey" in json.dumps(synthesis)
    rows = (tmp_path / DISCOVERY_LOG).read_text().splitlines()
    assert json.loads(rows[0])["query"] == "sparse attention"
    export_evidence(tmp_path, "metis_retrieval")
    evidence = json.loads((tmp_path / "retrieved-evidence.json").read_text())
    assert evidence[0]["retrieval"]["discovery"]["proposed_by"][0]["query"] == "sparse attention"
