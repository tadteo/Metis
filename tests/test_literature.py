from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from autoresearch.config import LiteratureConfig, ResearchConfig
from autoresearch.literature import (
    ArxivProvider,
    CrossrefProvider,
    Literature,
    ProviderResult,
    SemanticScholarProvider,
    arxiv_expression,
    keyword_query,
    novelty_coverage,
    query_terms,
)


def mock_network(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        "autoresearch.literature.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def paper(index=1, **kwargs):
    return Literature._evidence(
        {
            "title": f"Paper {index}",
            "url": f"https://arxiv.org/abs/2401.0000{index}v1",
            "provider": "fixture",
            "published_at": "2024-01-02",
            "abstract": "Measured result",
            **kwargs,
        }
    )


class FixtureProvider:
    name = "fixture"

    def __init__(self, papers):
        self.papers = papers

    def search(self, query, count, cutoff):
        return ProviderResult(
            self.papers[:count],
            100,
            json.dumps({"query": query}),
            "https://example.org/api",
            {"query": query},
        )


class FailedProvider:
    name = "failed"

    def search(self, query, count, cutoff):
        request = httpx.Request("GET", "https://example.org")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError(
            "secret header must not be logged", request=request, response=response
        )


def test_multiple_providers_keep_failures_exact_sources_and_limits():
    literature = Literature(
        ResearchConfig(literature=LiteratureConfig(full_text=False)),
        [FailedProvider(), FixtureProvider([paper(i) for i in range(1, 5)])],
    )
    sleeps: list[float] = []
    literature.sleep = sleeps.append
    results = literature.search("regression", 10)
    assert len(results) == 4
    report = literature.last_report
    assert report["providers"][0]["http_status"] == 429
    # A persistent 429 is retried a bounded number of times, then recorded as a failure.
    assert sleeps == [2.0, 4.0]
    assert [e["gave_up"] for e in report["providers"][0]["backoff"]] == [False, False, True]
    assert "secret" not in json.dumps(report)
    assert report["providers"][1]["raw_response"] == '{"query": "regression"}'
    assert report["providers"][1]["response_sha256"]
    assert not report["exhaustive"]
    assert report["limitations"]
    coverage = novelty_coverage(results, literature.search_history)
    assert coverage["sufficient_for_assessment"]
    assert not coverage["exhaustive"]
    assert not novelty_coverage(results[:2], literature.search_history)["sufficient_for_assessment"]


def test_cutoff_excludes_unknown_dates_future_and_future_revisions():
    evidence = [
        paper(1),
        paper(2, published_at=""),
        paper(3, published_at="2025-01-01"),
        paper(4, retrieval={"updated_at": "2026-01-01"}),
    ]
    literature = Literature(
        ResearchConfig(
            literature=LiteratureConfig(publication_cutoff="2024-12-31", full_text=False)
        ),
        [FixtureProvider(evidence)],
    )
    result = literature.search_external("test")
    assert [e.title for e in result] == ["Paper 1"]
    assert len(literature.last_report["excluded"]) == 3
    assert all("evidence" in x for x in literature.last_report["excluded"])


def test_crossref_retains_abstract_dates_and_source_record(monkeypatch):
    def handler(request):
        assert "until-pub-date:2025-01-01" == request.url.params["filter"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "total-results": 23,
                    "items": [
                        {
                            "title": ["A result"],
                            "URL": "https://doi.org/10.1/test",
                            "DOI": "10.1/test",
                            "abstract": "<jats:p>Measured gain</jats:p>",
                            "published": {"date-parts": [[2024]]},
                            "container-title": ["ICLR"],
                        }
                    ],
                }
            },
        )

    mock_network(monkeypatch, handler)
    result = CrossrefProvider().search("query", 12, "2025-01-01")
    assert result.papers[0].abstract == "Measured gain"
    assert result.papers[0].published_at == "2024-12-31"
    assert result.papers[0].retrieval["record"]["DOI"] == "10.1/test"
    assert result.total == 23


def test_semantic_scholar_abstract_and_open_access_link(monkeypatch):
    def handler(request):
        assert request.url.params["publicationDateOrYear"] == ":2025-01-01"
        return httpx.Response(
            200,
            json={
                "total": 1,
                "data": [
                    {
                        "paperId": "abc",
                        "title": "A result",
                        "abstract": "Experiment",
                        "externalIds": {"ArXiv": "2401.00001", "DOI": "10.1/test"},
                        "publicationDate": "2024-01-01",
                        "venue": "ICML",
                        "openAccessPdf": {"url": "https://arxiv.org/pdf/2401.00001"},
                    }
                ],
            },
        )

    mock_network(monkeypatch, handler)
    result = SemanticScholarProvider().search("method", 5, "2025-01-01")
    assert result.papers[0].identifiers["arxiv"] == "2401.00001"
    assert result.papers[0].abstract == "Experiment"
    assert result.papers[0].retrieval["open_access_pdf"].endswith("2401.00001")


def test_arxiv_atom_and_revision_date(monkeypatch):
    monkeypatch.setattr("autoresearch.literature.ARXIV_LAST_REQUEST", 0)
    xml = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><opensearch:totalResults>5</opensearch:totalResults><entry><id>http://arxiv.org/abs/2401.00001v2</id><title>A method</title><summary>Full abstract</summary><published>2024-01-01T00:00:00Z</published><updated>2024-02-01T00:00:00Z</updated></entry></feed>"""
    mock_network(monkeypatch, lambda request: httpx.Response(200, text=xml))
    result = ArxivProvider().search("method", 5, "2024-06-01")
    assert result.total == 5
    assert result.papers[0].retrieval["updated_at"] == "2024-02-01"
    assert result.papers[0].url.startswith("https://")
    assert "submittedDate:" in result.parameters["search_query"]


def test_arxiv_fulltext_is_inspected_hashed_and_truncation_visible(monkeypatch):
    def handler(request):
        assert str(request.url) == "https://arxiv.org/html/2401.00001v1"
        return httpx.Response(200, text="<article>" + "Measured gains. " * 1000 + "</article>")

    mock_network(monkeypatch, handler)
    literature = Literature(ResearchConfig(literature=LiteratureConfig(max_full_text_chars=1000)))
    result = literature.inspect(paper(identifiers={"arxiv": "2401.00001v1"}))
    assert len(result.full_text) == 1000
    assert result.retrieval["full_text_truncated"]
    assert result.retrieval["full_text_sha256"]
    assert result.full_text_url == "https://arxiv.org/html/2401.00001v1"


def test_unversioned_fulltext_cannot_leak_past_publication_cutoff(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("unversioned content must not be fetched under a cutoff")

    monkeypatch.setattr("autoresearch.literature.httpx.Client", blocked)
    literature = Literature(
        ResearchConfig(literature=LiteratureConfig(publication_cutoff="2024-01-01"))
    )
    result = literature.inspect(paper(identifiers={"arxiv": "2401.00001"}))
    assert not result.full_text
    assert "unversioned" in result.retrieval["full_text_status"]


def test_metadata_and_supplied_corpus_cannot_establish_novelty():
    assert not novelty_coverage([paper(i, abstract="", excerpt="") for i in range(4)], [{}])[
        "sufficient_for_assessment"
    ]
    assert not novelty_coverage([paper(i, provider="supplied") for i in range(4)], [{}])[
        "sufficient_for_assessment"
    ]


def test_search_report_denominator_includes_parallel_calls():
    literature = Literature(
        ResearchConfig(literature=LiteratureConfig(full_text=False)), [FixtureProvider([paper()])]
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(literature.search, ["first", "second", "third"]))
    assert {item["query"] for item in literature.search_history} == {"first", "second", "third"}


def test_arbitrary_search_endpoint_is_rejected():
    with pytest.raises(ValueError, match="Crossref adapter"):
        Literature(ResearchConfig(search_endpoint="https://localhost/private"))


def test_gzip_api_response_is_not_decompressed_twice(monkeypatch):
    import gzip

    payload = {
        "message": {
            "total-results": 1,
            "items": [{"title": ["Result"], "URL": "https://doi.org/10.1/result"}],
        }
    }
    mock_network(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            content=gzip.compress(json.dumps(payload).encode()),
            headers={"content-encoding": "gzip"},
        ),
    )
    result = CrossrefProvider().search("query", 3, "")
    assert result.papers[0].title == "Result"


def test_crossref_unknown_publication_date_is_retained_as_unknown(monkeypatch):
    mock_network(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "title": ["Undated"],
                            "URL": "https://doi.org/10.1/undated",
                            "published": {"date-parts": [[None]]},
                        }
                    ]
                }
            },
        ),
    )
    assert CrossrefProvider().search("query", 3, "").papers[0].published_at == ""


def test_cross_provider_doi_arxiv_aliases_do_not_inflate_novelty_coverage():
    first = paper(1, identifiers={"doi": "10.1/a", "arxiv": "2401.00001"})
    duplicate = paper(2, identifiers={"arxiv": "2401.00001v2"})
    second = paper(3, identifiers={"DOI": "10.1/b"})
    coverage = novelty_coverage([first, duplicate, second], [{}])
    assert coverage["independent_papers"] == 2
    assert not coverage["sufficient_for_assessment"]


def test_cross_query_aliases_survive_cache_and_serialized_evidence():
    from autoresearch.contracts import Evidence

    doi_record = paper(
        1,
        url="https://doi.org/10.1/a",
        identifiers={"doi": "10.1/a"},
        abstract="A longer independently retrieved abstract for the first paper",
    )
    bridge = paper(
        1,
        url="https://semanticscholar.org/paper/a",
        identifiers={"doi": "10.1/a", "arxiv": "2401.00001"},
        abstract="Short abstract",
    )
    arxiv_record = paper(1, identifiers={"arxiv": "2401.00001v1"})
    other = paper(2, identifiers={"doi": "10.1/b"})

    class QueryProvider(FixtureProvider):
        def search(self, query, count, cutoff):
            self.papers = [doi_record, bridge, other] if query == "first" else [arxiv_record]
            return super().search(query, count, cutoff)

    literature = Literature(
        ResearchConfig(literature=LiteratureConfig(full_text=False)), [QueryProvider([])]
    )
    initial = literature.search_external("first")
    cached = literature.search_external("first")
    assert [e.id for e in cached] == [e.id for e in initial]
    restored = [Evidence.model_validate_json(e.model_dump_json()) for e in cached]
    later = literature.search_external("second")
    coverage = novelty_coverage([*restored, *later], literature.search_history)
    assert coverage["independent_papers"] == 2
    assert coverage["inspectable_papers"] == 2
    assert not coverage["sufficient_for_assessment"]
    merged = next(e for e in initial if e.identifiers.get("doi") == "10.1/a")
    assert merged.identifiers["arxiv"] == "2401.00001"
    assert {source["id"] for source in merged.retrieval["merged_sources"]} == {
        doi_record.id,
        bridge.id,
    }


@pytest.mark.parametrize("independent_abstract", ["Independent abstract", ""])
def test_supplied_duplicate_does_not_replace_or_launder_independent_content(independent_abstract):
    supplied = paper(
        1,
        provider="supplied",
        identifiers={"doi": "10.1/a"},
        full_text="Much longer user-supplied full text, not independently inspected.",
        abstract="Unverified supplied abstract",
    )
    independent = paper(
        1,
        provider="crossref",
        identifiers={"doi": "10.1/a"},
        abstract=independent_abstract,
    )
    literature = Literature(
        ResearchConfig(
            references=[supplied.model_dump(exclude={"identifiers", "retrieval"})],
            literature=LiteratureConfig(full_text=False),
        ),
        [FixtureProvider([independent])],
    )
    results = literature.search("verify supplied citation")
    assert len(results) == 1
    merged = results[0]
    assert merged.provider == "crossref"
    assert merged.abstract == independent_abstract
    assert not merged.full_text
    sources = merged.retrieval["merged_sources"]
    assert {source["provider"] for source in sources} == {"supplied", "crossref"}
    assert all(source["content_hash"] for source in sources)
    coverage = novelty_coverage(results, literature.search_history)
    assert coverage["independent_papers"] == 1
    assert coverage["inspectable_papers"] == bool(independent_abstract)
    cached_results = literature.search("verify supplied citation")
    assert cached_results[0].id == merged.id
    assert cached_results[0].retrieval["merged_sources"] == sources


def test_metadata_only_bridge_still_connects_inspectable_copies_for_coverage():
    first = paper(1, url="https://doi.org/10.1/a", identifiers={"doi": "10.1/a"})
    bridge = paper(
        2,
        url="https://semanticscholar.org/paper/a",
        identifiers={"doi": "10.1/a", "arxiv": "2401.00001"},
        abstract="",
    )
    copy = paper(3, identifiers={"arxiv": "2401.00001"})
    other = paper(4, identifiers={"doi": "10.1/b"})
    coverage = novelty_coverage([first, bridge, copy, other], [{}])
    assert coverage["independent_papers"] == 2
    assert coverage["inspectable_papers"] == 2
    assert not coverage["sufficient_for_assessment"]


# Synthetic hypothesis-length query shaped like the failing live novelty search
# (title + hypothesis sentence with stopwords, code tokens and numbers).
HYPOTHESIS_QUERY = (
    "Polynomial Feature Expansion with L2 Regularization Increasing polynomial degree from 1 "
    "to a low-order nonlinear expansion (degree 2-3) with a ridge penalty tuned in train.py "
    "will surpass the linear baseline on the held-out split; learning_rate=1e-3, seed 42."
)


def test_query_terms_drop_stopwords_code_tokens_and_numbers():
    terms = query_terms(HYPOTHESIS_QUERY)
    assert terms[:5] == ["polynomial", "feature", "expansion", "l2", "regularization"]
    assert "low-order" in terms  # hyphenated compounds stay together as phrases
    assert len(terms) == 8
    dropped = {"with", "the", "will", "to", "a", "py", "train", "learning_rate", "1e-3", "42", "1"}
    assert not dropped & set(terms)
    assert query_terms("graph neural networks") == ["graph", "neural", "networks"]
    assert query_terms("the of") == ["the", "of"]  # never an empty query
    assert keyword_query(HYPOTHESIS_QUERY).startswith("polynomial feature expansion l2 ")
    assert keyword_query(HYPOTHESIS_QUERY).endswith(" degree low order")
    # Titles and other short queries are sent as written (citation title lookup).
    assert keyword_query("Attention Is All You Need") == "Attention Is All You Need"


def test_arxiv_hypothesis_query_is_bounded_not_thirty_anded_terms(monkeypatch):
    monkeypatch.setattr("autoresearch.literature.ARXIV_LAST_REQUEST", 0)
    monkeypatch.setattr("autoresearch.literature.time.sleep", lambda seconds: None)
    sent = []
    xml = (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
        "<opensearch:totalResults>0</opensearch:totalResults></feed>"
    )

    def handler(request):
        sent.append(request.url.params["search_query"])
        return httpx.Response(200, text=xml)

    mock_network(monkeypatch, handler)
    result = ArxivProvider().search(HYPOTHESIS_QUERY, 12, "2026-01-01")
    expression = sent[0]
    assert expression == result.parameters["search_query"]
    assert expression.count("all:") == 8  # previously one ANDed all: term per word (~30)
    # Three required core terms, the rest an optional relevance group, then the cutoff.
    assert expression.startswith("all:polynomial AND all:feature AND all:expansion AND (all:l2 OR ")
    assert 'all:"low order"' in expression
    assert expression.count(" AND ") == 4
    for noise in ("all:with ", "all:the ", "all:will ", "all:py", "all:1 ", "all:42"):
        assert noise not in expression
    assert arxiv_expression("Graph networks") == "all:Graph AND all:networks"


def test_semantic_scholar_429_then_success_honours_retry_after_and_records_queries(
    monkeypatch,
):
    statuses = [429, 200]
    sent = []

    def handler(request):
        sent.append(request.url.params["query"])
        status = statuses.pop(0)
        if status == 429:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={})
        return httpx.Response(
            200,
            json={
                "total": 1,
                "data": [
                    {
                        "paperId": "abc",
                        "title": "Ridge polynomial features",
                        "abstract": "Measured comparison",
                        "url": "https://www.semanticscholar.org/paper/abc",
                        "externalIds": {"DOI": "10.1/ridge"},
                        "publicationDate": "2024-01-01",
                    }
                ],
            },
        )

    mock_network(monkeypatch, handler)
    literature = Literature(
        ResearchConfig(literature=LiteratureConfig(full_text=False)), [SemanticScholarProvider()]
    )
    sleeps: list[float] = []
    literature.sleep = sleeps.append  # fake clock: no real waiting in tests
    papers = literature.search_external(HYPOTHESIS_QUERY, 12)
    assert [p.title for p in papers] == ["Ridge polynomial features"]
    assert sleeps == [7.0]
    report = literature.last_report
    detail = report["providers"][0]
    assert detail["status"] == "completed"
    assert detail["backoff"] == [
        {
            "attempt": 1,
            "error": "HTTPStatusError",
            "http_status": 429,
            "retry_after": 7.0,
            "wait_seconds": 7.0,
            "gave_up": False,
        }
    ]
    # Provenance keeps both the raw query and the derived provider query.
    assert report["query"] == HYPOTHESIS_QUERY
    assert report["keyword_query"] == keyword_query(HYPOTHESIS_QUERY)
    assert detail["provider_query"] == sent[0] == sent[1] == keyword_query(HYPOTHESIS_QUERY)
    assert detail["parameters"]["query"] == keyword_query(HYPOTHESIS_QUERY)


def test_transient_backoff_is_bounded_capped_and_skips_permanent_errors(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "api.crossref.org":
            return httpx.Response(400, json={})  # permanent: no retry
        return httpx.Response(503, headers={"Retry-After": "3600"}, json={})

    mock_network(monkeypatch, handler)
    literature = Literature(
        ResearchConfig(literature=LiteratureConfig(full_text=False)),
        [SemanticScholarProvider(), CrossrefProvider()],
    )
    sleeps: list[float] = []
    literature.sleep = sleeps.append
    assert literature.search_external("ridge regression", 12) == []
    assert sleeps == [60.0, 60.0]  # Retry-After honoured but each wait capped; never infinite
    s2, crossref = literature.last_report["providers"]
    assert [e["gave_up"] for e in s2["backoff"]] == [False, False, True]
    assert s2["http_status"] == 503 and s2["provider_query"] == "ridge regression"
    assert crossref["backoff"] == [
        {
            "attempt": 1,
            "error": "HTTPStatusError",
            "http_status": 400,
            "retry_after": None,
            "wait_seconds": 0.0,
            "gave_up": True,
        }
    ]
    assert calls.count("api.crossref.org") == 1


def test_novelty_fetches_more_candidates_than_the_minimum(tmp_path, monkeypatch):
    from autoresearch.contracts import AgentOutput, Evidence, Idea, Stage
    from autoresearch.engine import Engine
    from autoresearch.research_stages.seeds import novelty_fetch_count
    from autoresearch.store import Store

    config = ResearchConfig(literature=LiteratureConfig(full_text=False))
    config.pipeline.novelty_references = 2
    config.pipeline.novelty_queries = 1
    assert novelty_fetch_count(config) == 12  # one provider page, not the minimum of 2
    config.literature.max_results = 5
    assert novelty_fetch_count(config) == 5  # still bounded by max_results
    config.literature.max_results = 40
    calls = []

    class Retriever:
        search_history = [{"query": "fixture", "providers": []}]

        def behavior_identity(self):
            return {"fixture": "fetch-count", "version": 1}

        def search(self, query, count):
            calls.append(count)
            return [
                Evidence(
                    id=str(i),
                    title=f"Independent {i}",
                    url=f"https://example.org/{i}",
                    provider="fixture",
                    abstract="Inspectable independent content",
                )
                for i in range(count)
            ]

    store = Store(tmp_path)
    engine = Engine(store, config, literature=Retriever())
    state = engine.create("Fixture", "Exercise retrieval count")
    state.stage = Stage.NOVELTY
    state.ideas = [
        Idea(id="candidate", title="Candidate", hypothesis="Mechanism", status="pending_novelty")
    ]
    store.save(state)
    monkeypatch.setattr(
        engine, "_judge", lambda *a, **kw: AgentOutput(summary="fixture", decision="reject")
    )
    engine.step(state.id)
    assert calls == [12]
