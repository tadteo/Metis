from typing import Any

import httpx
import pytest

from autoresearch.config import LiteratureConfig, ResearchConfig
from autoresearch.contracts import AgentOutput, Evidence, RunState
from autoresearch.literature import Literature
from autoresearch.references import audit_references
from autoresearch.review import review_context


class FixtureLiterature(Literature):
    def __init__(self):
        super().__init__(ResearchConfig())
        self.queries: list[str] = []

    def search(self, query: str, count: int = 2) -> list[Evidence]:
        return self.search_external(query, count)

    def search_external(self, query: str, count: int = 2) -> list[Evidence]:
        self.queries.append(query)
        return [
            Evidence(
                id="verified",
                title="Verified primary reference",
                url="https://doi.org/10.1234/example",
                published_at="2024-01-01",
                abstract="An independently measured result.",
                provider="fixture",
                retrieval={"venue": "ICLR"},
            )
        ]


def test_scholarpeer_reconstruction_executes_all_subsystems():
    seen = []

    def call(role: str, context: dict[str, Any]) -> AgentOutput:
        seen.append(role)
        assert context["published_prompt"]
        assert context["publication_cutoff"]
        if role.endswith("questions"):
            return AgentOutput(
                summary=role,
                plans=[{"question": f"Claim {i}: Is the advance novel?"} for i in range(5)],
            )
        if role == "review_literature":
            return AgentOutput(summary=role, plans=[{"question": "Find missing foundational work"}])
        return AgentOutput(
            summary=role,
            evidence_ids=["verified"] if role == "review_novelty_answers" else [],
            structured={
                "claims": ["measured gain"],
                "method": "regression",
                "evidence": ["experiment-1"],
            },
        )

    literature = FixtureLiterature()
    result = review_context(
        RunState(id="test", title="Regression", objective="Research"), call, literature, 2
    )
    assert set(seen) == {
        "review_summary",
        "review_literature",
        "review_expansion",
        "review_historian",
        "review_baseline_scout",
        "review_novelty_questions",
        "review_technical_questions",
        "review_novelty_answers",
        "review_technical_answers",
    }
    assert set(result["qa"]) == {"novelty", "technical"}
    assert len(literature.queries) == 10
    assert len(result["expansion_rounds"]) == 3
    assert len(result["qa_pairs"]) == 10
    assert len(result["individual_outputs"]) == 19
    assert not result["held_out"]
    assert result["prompt_provenance"]["license"] == "CC-BY-4.0"
    assert not result["literature_coverage"]["exhaustive"]
    assert result["review_evidence"][0]["id"] == "verified"


def test_reference_audit_rejects_unknown_and_absent_citations():
    literature = FixtureLiterature()
    evidence = literature.search("reference")
    assert audit_references("No citations", evidence, literature).issues
    assert audit_references("https://unknown.example/paper", evidence, literature).issues
    assert audit_references("[@missing]", evidence, literature).issues
    assert audit_references("[@verified]", evidence, literature).verified == ["verified"]
    assert not audit_references("https://doi.org/10.1234/example", evidence, literature).issues


def test_supplied_reference_cannot_verify_itself_with_search_disabled(monkeypatch):
    def unexpected_network(*args, **kwargs):
        raise AssertionError("disabled search must not access the network")

    monkeypatch.setattr("autoresearch.literature.httpx.Client", unexpected_network)
    literature = Literature(
        ResearchConfig(
            search_enabled=False,
            references=[
                {
                    "title": "Nonexistent supplied reference",
                    "url": "https://example.invalid/nonexistent-paper",
                }
            ],
        )
    )
    evidence = literature.search("supplied paper")
    assert len(evidence) == 1  # Available context is not independent verification.
    audit = audit_references(f"[@{evidence[0].id}]", evidence, literature)
    assert not audit.verified
    assert audit.issues == [f"Citation could not be independently re-retrieved: {evidence[0].id}"]


def test_external_retrieval_does_not_reinsert_supplied_corpus(monkeypatch):
    real_client = httpx.Client

    def handler(request):
        assert request.url.host == "api.crossref.org"
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "title": ["Independently found reference"],
                            "URL": "https://doi.org/10.1234/found",
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(
        "autoresearch.literature.httpx.Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    literature = Literature(
        ResearchConfig(
            literature=LiteratureConfig(providers=["crossref"], full_text=False),
            references=[
                {"title": "Supplied invention", "url": "https://example.invalid/invention"}
            ],
        )
    )
    evidence = literature.search("references")
    assert len(evidence) == 2
    audit = audit_references(" ".join(f"[@{item.id}]" for item in evidence), evidence, literature)
    assert audit.verified == [evidence[1].id]
    assert audit.issues == [f"Citation could not be independently re-retrieved: {evidence[0].id}"]


def test_review_rejects_unstructured_extraction():
    with pytest.raises(ValueError, match="structured extraction"):
        review_context(
            RunState(id="review", title="Paper", objective="review"),
            lambda role, context: AgentOutput(summary="No extraction"),
            Literature(ResearchConfig(search_enabled=False)),
            1,
        )


def test_prompt_assets_are_verified_and_rendered():
    from autoresearch.review import PROMPT_MANIFEST, load_published_prompt, render_published_prompt

    for role in PROMPT_MANIFEST["prompts"]:
        assert load_published_prompt(role)
    rendered = render_published_prompt("review_summary", {"paper_text": "This is the paper"})
    assert "{paper_text}" not in rendered
    assert "This is the paper" in rendered
    with pytest.raises(ValueError, match="missing"):
        render_published_prompt("review_summary", {})


def test_latex_citations_resolve_retrieved_bibtex_keys():
    literature = FixtureLiterature()
    reference = literature.search("reference")[0]
    reference.identifiers["bibtex"] = "Author2024Result"
    result = audit_references(
        r"Measured result \citep[see][Sec. 3]{Author2024Result}. Other result \citet*{Author2024Result}.",
        [reference],
        literature,
    )
    assert result.verified == [reference.id]
    assert not result.issues
    assert (
        "Unknown citation ID: Invented2024"
        in audit_references(r"\cite{Author2024Result,Invented2024}", [reference], literature).issues
    )


def test_latex_comment_citation_cannot_validate_uncited_manuscript():
    literature = FixtureLiterature()
    reference = literature.search("reference")[0]
    assert not audit_references(
        "No citations\n% \\cite{verified}", [reference], literature
    ).verified


def test_independent_doi_match_survives_different_provider_url():
    literature = FixtureLiterature()
    reference = Evidence(
        id="writer",
        title="Verified primary reference",
        url="https://www.semanticscholar.org/paper/test",
        identifiers={"DOI": "10.1234/example", "bibtex": "writer2024"},
    )
    original = literature.search_external

    def external(query, count=5):
        result = original(query, count)
        result[0].identifiers["doi"] = "10.1234/example"
        return result

    literature.search_external = external
    result = audit_references(r"\cite{writer2024}", [reference], literature)
    assert result.verified == ["writer"]


def test_semantic_review_failure_repairs_then_escalates_and_retains_failed_outputs():
    from autoresearch.contracts import ProviderConfig

    literature = FixtureLiterature()
    literature.config.frontier_provider = ProviderConfig(model="frontier-test")
    summary_contexts = []

    def call(role, context):
        if role == "review_summary":
            summary_contexts.append(context)
            if not context.get("escalate"):
                return AgentOutput(summary="Invalid structure from cheap route")
        if role.endswith("questions"):
            return AgentOutput(
                summary=role, plans=[{"question": f"Distinct question {i}?"} for i in range(5)]
            )
        return AgentOutput(
            summary=role,
            evidence_ids=["verified"] if role == "review_novelty_answers" else [],
            structured={
                "claims": ["claim"],
                "method": "method",
                "evidence": ["experiment"],
                "references": [{"title": role}],
            },
        )

    result = review_context(
        RunState(id="review", title="Paper", objective="Review"), call, literature, 1
    )
    assert len(summary_contexts) == 4
    assert summary_contexts[-1]["escalate"]
    assert all("validation_error" in item for item in result["individual_outputs"][:3])
    assert result["literature"]["references"][0]["title"] == "review_literature"
    assert len(result["literature"]["references"]) == 4


def test_scientific_fields_named_like_transport_are_preserved():
    from autoresearch.review import retrieval_model_view

    original = {
        "raw_response": "a scientific measurement",
        "retrieval": {"record": {"abstract": "scientific record"}, "response_sha256": "hash"},
        "abstract": "Useful abstract",
        "excerpt": "Useful abstract",
        "full_text": "All inspected full text",
        "limitations": ["rate limited"],
    }
    assert retrieval_model_view(original) == original


def test_markdown_percentages_do_not_comment_out_following_citations():
    literature = FixtureLiterature()
    reference = literature.search("reference")[0]
    result = audit_references("Accuracy is 51% compared with [@verified].", [reference], literature)
    assert result.verified == [reference.id]
    assert not result.issues


@pytest.mark.parametrize(
    "slashes,expected", [(1, ["verified"]), (2, []), (3, ["verified"]), (4, [])]
)
def test_latex_percent_comment_uses_backslash_parity(slashes, expected):
    literature = FixtureLiterature()
    reference = literature.search("reference")[0]
    manuscript = "Result " + "\\" * slashes + r"% compared with \cite{verified}."
    assert audit_references(manuscript, [reference], literature).verified == expected
