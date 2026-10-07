"""D04 opt-in substitution of the writer's Google-grounded literature discovery.

No network or model calls: retrieval providers and upstream-shaped agents are fakes.
The actual pinned agent is exercised in tests/test_writing_upstream.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from autoresearch.config import LiteratureConfig, ResearchConfig
from autoresearch.literature import Literature, ProviderResult, _evidence
from autoresearch.paper_orchestra import (
    PaperOrchestraConfig,
    PaperOrchestraError,
    _command,
    preflight_writer,
    resolve_writer_config,
)
from autoresearch.paper_orchestra_worker import (
    DISCOVERY_LOG,
    DISCOVERY_SUMMARY,
    CallJournal,
    MetisLiteratureDiscovery,
    StageJournal,
    discovery_agent,
    export_evidence,
)

GROUNDING_ERROR = (
    "GEMINI_API_KEY required for native grounded literature search and image generation"
)


class FakeProvider:
    name = "semantic_scholar"

    def __init__(self, titles: list[str] | None = None, fail: bool = False):
        self.titles = titles if titles is not None else []
        self.fail = fail
        self.queries: list[tuple[str, int, str]] = []

    def search(self, query: str, count: int, cutoff: str) -> ProviderResult:
        self.queries.append((query, count, cutoff))
        if self.fail:
            raise httpx.ConnectError("synthetic outage")
        papers = [
            _evidence(
                {
                    "title": title,
                    "url": f"https://example.org/paper/{index}",
                    "abstract": "Synthetic abstract",
                    "provider": self.name,
                    "identifiers": {"doi": f"10.0/synthetic.{index}"},
                    "published_at": "2024-05-01",
                }
            )
            for index, title in enumerate(self.titles[:count])
        ]
        body = json.dumps({"data": [p.title for p in papers]})
        return ProviderResult(papers, len(self.titles), body, "https://fake.invalid/search", {})


def metis_config(**writer: Any) -> ResearchConfig:
    return ResearchConfig(
        paper_orchestra=PaperOrchestraConfig(literature_discovery="metis_retrieval", **writer),
        literature=LiteratureConfig(providers=["semantic_scholar"]),
    )


def worker_options(**overrides: Any) -> dict[str, Any]:
    options = resolve_writer_config(metis_config())
    options.update(research_cutoff="2026-09", **overrides)
    return options


def discovery(tmp_path: Path, provider: FakeProvider) -> MetisLiteratureDiscovery:
    options = worker_options()
    config = ResearchConfig(literature=LiteratureConfig(providers=["semantic_scholar"]))
    return MetisLiteratureDiscovery(
        tmp_path,
        options,
        CallJournal(tmp_path, options),
        lambda: Literature(config, providers=[provider]),
    )


class OfficialShapedAgent:
    """Reproduces only the pinned call structure: discovered candidates feed enrichment."""

    def __init__(self) -> None:
        self.enriched: list[tuple[Any, dict[str, Any]]] = []

    def run(self, tasks: list[dict[str, Any]]) -> None:
        for task in tasks:
            try:  # Upstream swallows discovery exceptions and retries up to three times.
                candidates = self._discover_candidates(task, {}, "2026-09")
            except Exception:  # noqa: BLE001 - mirrors upstream behavior under test.
                candidates = []
            self.enriched.extend((candidate, task) for candidate in candidates)

    def _discover_candidates(
        self, task: dict[str, Any], outline: dict[str, Any], cutoff_date: str
    ) -> list[Any]:
        raise AssertionError("Google-grounded discovery must not run under metis_retrieval")


TASKS = [
    {"section": "Introduction", "focus": "sparse attention", "search_type": "exploration"},
    {"section": "Method - Base", "focus": "original transformer", "search_type": "targeted"},
]


def test_default_mode_is_unchanged_and_requires_grounding_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "synthetic-provider-key")
    options = resolve_writer_config(ResearchConfig())
    assert "literature_discovery" not in options and "metis_literature" not in options
    assert options["literature_model_name"] == "gemini-3.1-pro-preview"
    report = preflight_writer(ResearchConfig())
    assert GROUNDING_ERROR in report["errors"]
    assert report["literature_discovery"] == "google_grounded"


def test_metis_retrieval_preflight_does_not_require_grounding_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = metis_config(use_plotting=False, literature_model_name="")
    monkeypatch.setenv(config.provider.api_key_env, "synthetic-provider-key")
    report = preflight_writer(config)
    assert not any("GEMINI_API_KEY" in error for error in report["errors"])
    assert report["literature_discovery"] == "metis_retrieval"
    options = resolve_writer_config(config)
    assert options["literature_model_name"] == options["writer_model_name"]
    assert options["literature_model_name"] in options["compatible_models"]
    assert report["unpriced_native_models"] == ["gemini-3-pro-image-preview"]
    # Native image generation and native text models still need the Gemini key.
    plotting = preflight_writer(metis_config(literature_model_name=""))
    assert any("native image generation" in error for error in plotting["errors"])
    native = preflight_writer(metis_config(use_plotting=False))
    assert any("native model gemini-3.1-pro-preview" in e for e in native["errors"])
    disabled = metis_config(use_plotting=False, literature_model_name="")
    disabled.search_enabled = False
    assert any("search_enabled" in e for e in preflight_writer(disabled)["errors"])


def test_job_identity_includes_discovery_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default = resolve_writer_config(ResearchConfig())
    substituted = resolve_writer_config(metis_config())
    assert substituted["literature_discovery"] == "metis_retrieval"
    assert substituted["metis_literature"]["literature"]["providers"] == ["semantic_scholar"]
    # run_official_writer fingerprints the complete resolved options.
    assert json.dumps(default, sort_keys=True) != json.dumps(substituted, sort_keys=True)
    narrower = ResearchConfig(
        paper_orchestra=PaperOrchestraConfig(literature_discovery="metis_retrieval"),
        literature=LiteratureConfig(providers=["arxiv"]),
    )
    assert resolve_writer_config(narrower) != substituted
    # A configured retrieval credential name reaches the worker only in substitution mode.
    monkeypatch.setenv("CUSTOM_S2_KEY", "synthetic-s2-key")
    custom = ResearchConfig(
        paper_orchestra=PaperOrchestraConfig(literature_discovery="metis_retrieval"),
        literature=LiteratureConfig(semantic_scholar_api_key_env="CUSTOM_S2_KEY"),
    )
    _, env = _command(tmp_path, tmp_path / "upstream", resolve_writer_config(custom))
    assert env["CUSTOM_S2_KEY"] == "synthetic-s2-key"
    _, env = _command(tmp_path, tmp_path / "upstream", default)
    assert "CUSTOM_S2_KEY" not in env


def test_discovery_routes_official_queries_and_feeds_downstream(tmp_path: Path) -> None:
    provider = FakeProvider(["Sparse Attention Survey", "Attention Is All You Need"])
    adapter = discovery(tmp_path, provider)
    agent = discovery_agent(OfficialShapedAgent, adapter)()
    StageJournal(tmp_path).run("literature", lambda: agent.run(TASKS), [])
    adapter.finish()
    # The exact official task foci are the retrieval queries, with the writer cutoff.
    assert [q[0] for q in provider.queries] == ["sparse attention", "original transformer"]
    assert {q[2] for q in provider.queries} == {"2026-09-30"}
    titles = [candidate["title"] for candidate, _ in agent.enriched]
    assert titles == [
        "Sparse Attention Survey",
        "Attention Is All You Need",
        "Sparse Attention Survey",
    ]
    assert all(set(c) == {"title", "year", "reason"} for c, _ in agent.enriched)
    assert agent.enriched[0][0]["year"] == 2024
    rows = [json.loads(x) for x in (tmp_path / DISCOVERY_LOG).read_text().splitlines()]
    assert [row["status"] for row in rows] == ["completed", "completed"]
    first = rows[0]
    assert first["backend"] == "metis_retrieval" and first["deviation"] == "D04"
    assert first["stage"] == "literature" and first["query"] == "sparse attention"
    assert first["started_at"] and first["completed_at"]
    detail = first["report"]["providers"][0]
    assert detail["provider"] == "semantic_scholar" and detail["raw_response"]
    assert first["candidates"][0]["identifiers"] == {"doi": "10.0/synthetic.0"}
    summary = json.loads((tmp_path / DISCOVERY_SUMMARY).read_text())
    assert summary["novelty_certified"] is False
    assert summary["parity_with_google_grounding_measured"] is False
    assert summary["candidate_count"] == 3 and len(summary["requests"]) == 2
    assert any("not exhaustive" in item for item in summary["coverage_limitations"])
    receipts = (tmp_path / "requests.jsonl").read_text()
    assert '"provider": "metis-literature"' in receipts


def test_resumed_discovery_replays_retained_retrieval(tmp_path: Path) -> None:
    provider = FakeProvider(["Sparse Attention Survey"])
    discovery(tmp_path, provider).discover(TASKS[0])
    replay = discovery(tmp_path, provider)
    assert replay.discover(TASKS[0])[0]["title"] == "Sparse Attention Survey"
    assert len(provider.queries) == 1
    rows = [json.loads(x) for x in (tmp_path / DISCOVERY_LOG).read_text().splitlines()]
    assert rows[-1]["status"] == "replayed"


def test_empty_retrieval_fails_explicitly_and_never_certifies_novelty(tmp_path: Path) -> None:
    adapter = discovery(tmp_path, FakeProvider([]))
    agent = discovery_agent(OfficialShapedAgent, adapter)()
    agent.run(TASKS)
    assert agent.enriched == []
    with pytest.raises(PaperOrchestraError, match="no candidate papers"):
        adapter.finish()
    summary = json.loads((tmp_path / DISCOVERY_SUMMARY).read_text())
    assert summary["candidate_count"] == 0 and summary["novelty_certified"] is False
    assert any("insufficient" in item for item in summary["coverage_limitations"])


def test_provider_outage_is_recorded_and_blocks_literature_checkpoint(tmp_path: Path) -> None:
    adapter = discovery(tmp_path, FakeProvider(fail=True))
    agent = discovery_agent(OfficialShapedAgent, adapter)()
    output = tmp_path / "citation_map.json"

    def upstream() -> None:
        agent.run(TASKS)  # Upstream swallows the exception and continues.
        output.write_text("{}")

    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("literature", upstream, [output])
    assert not (tmp_path / "checkpoint.json").exists()
    rows = [json.loads(x) for x in (tmp_path / DISCOVERY_LOG).read_text().splitlines()]
    assert {row["status"] for row in rows} == {"failed"}
    assert rows[0]["report"]["providers"][0]["error"] == "ConnectError"
    assert not list((tmp_path / "discovery_cache").iterdir())


def test_exported_evidence_retains_discovery_provenance(tmp_path: Path) -> None:
    adapter = discovery(tmp_path, FakeProvider(["Sparse Attention Survey"]))
    adapter.discover(TASKS[0])
    (tmp_path / "search_cache").mkdir()
    s2 = {"title": "Sparse Attention Survey", "paperId": "abc", "abstract": "Synthetic"}
    (tmp_path / "search_cache/x.json").write_text(
        json.dumps(
            {
                "params": {"query": "Sparse Attention Survey"},
                "body": json.dumps({"data": [s2]}),
                "retrieved_at": 1.0,
            }
        )
    )
    (tmp_path / "literature").mkdir()
    (tmp_path / "literature/citation_map.json").write_text(
        json.dumps({"Key2024Sparse": {"title": "Sparse Attention Survey"}})
    )
    export_evidence(tmp_path, "metis_retrieval")
    record = json.loads((tmp_path / "retrieved-evidence.json").read_text())[0]
    provenance = record["retrieval"]["discovery"]
    assert provenance["backend"] == "metis_retrieval" and provenance["deviation"] == "D04"
    assert provenance["proposed_by"][0]["query"] == "sparse attention"
    assert record["provider"] == "paper-orchestra/semantic-scholar"
    export_evidence(tmp_path)
    default = json.loads((tmp_path / "retrieved-evidence.json").read_text())[0]
    assert "discovery" not in default["retrieval"]


def _module(name: str, **attributes: Any) -> Any:
    import types

    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    return module


def test_worker_execute_wires_substitution_and_marks_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise worker._execute wiring with stub SDKs and upstream-shaped agents."""
    import sys

    from autoresearch import paper_orchestra_worker as worker
    from autoresearch.paper_orchestra import UPSTREAM_REVISION

    base = tmp_path / "job"
    (base / "raw_materials/figures").mkdir(parents=True)
    (base / "template").mkdir()
    for name in ("raw_materials/idea_sparse.md", "raw_materials/experimental_log.md"):
        (base / name).write_text("Measured input")
    for name in ("template/template.tex", "template/guidelines.md"):
        (base / name).write_text("template")
    (base / "raw_materials/figures/info.json").write_text("[]")
    options = worker_options(use_plotting=False, literature_model_name="")
    (base / "job.json").write_text(
        json.dumps({"schema_version": 1, "revision": UPSTREAM_REVISION, "options": options})
    )
    grounded: list[Any] = []

    class Outline:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run(self, output_filepath: str, **kwargs: Any) -> None:
            Path(output_filepath).write_text("{}")

    class HybridLiteratureAgent:
        def __init__(self, output_dir: str, **kwargs: Any) -> None:
            self.output = Path(output_dir)
            self.output.mkdir(exist_ok=True)

        def run(self, outline_path: str, cutoff_date: str) -> None:
            task = {"section": "Introduction", "focus": "sparse attention"}
            titles = [c["title"] for c in self._discover_candidates(task, {}, cutoff_date)]
            # Stand-in for upstream's instrumented S2 title verification record.
            (base / "search_cache").mkdir(exist_ok=True)
            data = [{"title": t, "paperId": "p", "abstract": "A"} for t in titles]
            (base / "search_cache/s2.json").write_text(
                json.dumps(
                    {
                        "params": {"query": titles[0]},
                        "body": json.dumps({"data": data}),
                        "retrieved_at": 1.0,
                    }
                )
            )
            for name in ("outline_v1.json", "updated_template.tex", "references.bib"):
                (self.output / name).write_text("{}")
            (self.output / "citation_map.json").write_text(
                json.dumps({f"K{i}": {"title": t} for i, t in enumerate(titles)})
            )

        def _discover_candidates(self, task: Any, outline: Any, cutoff: str) -> list[Any]:
            grounded.append(task)
            return []

    class Sections:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run(self, output_path: str) -> None:
            Path(output_path).write_text("draft")

    class Refinement:
        def __init__(self, work_dir: str, **kwargs: Any) -> None:
            self.work = Path(work_dir)

        def run(self, texfile_path: str) -> str:
            (self.work / "final_refined_paper.tex").write_text("final")
            (self.work / "paper.pdf").write_bytes(b"%PDF")
            return str(self.work / "paper.pdf")

    def compile_stub(_: Path) -> Any:
        return lambda work, pdf, name: Path(pdf).write_bytes(b"%PDF-final")

    stubs = {
        "dotenv": _module("dotenv", load_dotenv=lambda *a, **k: True),
        "google": _module("google"),
        "google.genai": _module("google.genai", Client=object),
        "openai": _module("openai", OpenAI=object),
        "requests": _module("requests", get=lambda *a, **k: None),
        "utils": _module("utils"),
        "utils.pdf_utils": _module("utils.pdf_utils"),
        "methods": _module("methods"),
        "methods.agents": _module("methods.agents"),
        "methods.agents.outline_agent": _module("o", OutlineAgent=Outline),
        "methods.agents.literature_review_agent": _module(
            "l", HybridLiteratureAgent=HybridLiteratureAgent
        ),
        "methods.agents.section_writing_agent": _module("s", SectionWritingAgent=Sections),
        "methods.agents.content_refinement_agent": _module("c", ContentRefinementAgent=Refinement),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    for attribute in ("stdout", "stderr", "pycache_prefix"):
        monkeypatch.setattr(sys, attribute, getattr(sys, attribute))
    monkeypatch.setattr(sys, "path", list(sys.path))
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)
    monkeypatch.setattr(worker, "strict_compile", compile_stub)
    provider = FakeProvider(["Sparse Attention Survey"])
    config = ResearchConfig(literature=LiteratureConfig(providers=["semantic_scholar"]))
    monkeypatch.setattr(
        worker, "_metis_literature", lambda settings: Literature(config, providers=[provider])
    )
    worker.execute(base, tmp_path / "upstream")
    assert grounded == []  # The pinned discovery method was overridden, not called.
    assert provider.queries[0][0] == "sparse attention"
    checkpoint = json.loads((base / "checkpoint.json").read_text())
    assert DISCOVERY_SUMMARY in checkpoint["stages"]["literature"]["artifacts"]
    completed = json.loads((base / "completed.json").read_text())
    assert completed["literature_discovery"] == {"backend": "metis_retrieval", "deviation": "D04"}
    evidence = json.loads((base / "retrieved-evidence.json").read_text())
    assert evidence[0]["retrieval"]["discovery"]["backend"] == "metis_retrieval"
