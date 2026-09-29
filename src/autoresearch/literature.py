"""Bounded, inspectable scholarly retrieval; retrieved text is untrusted evidence.

Adapters retain records and query diagnostics. A successful query never establishes
exhaustive coverage. Network failures and unknown publication dates are explicit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from .config import ResearchConfig
from .contracts import Evidence

MAX_RESPONSE_BYTES = 4_000_000
ARXIV_LOCK = threading.Lock()
ARXIV_LAST_REQUEST = 0.0


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.ignored:
            self.ignored -= 1
        if tag in {"p", "div", "section", "tr", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()


def _date(parts: list[int | None]) -> str:
    if not parts or not isinstance(parts[0], int) or not 1 <= parts[0] <= 9999:
        return ""
    # Uncertain dates use the end of the known interval to avoid cutoff leakage.
    year = parts[0]
    if len(parts) == 1 or not isinstance(parts[1], int):
        return f"{year:04d}-12-31"
    month = parts[1]
    if not 1 <= month <= 12:
        return ""
    import calendar

    day = (
        parts[2]
        if len(parts) > 2 and isinstance(parts[2], int)
        else calendar.monthrange(year, month)[1]
    )
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _get(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
    # Fixed API endpoints / allowlisted fulltext only, and no automatic redirects.
    with client.stream("GET", url, **kwargs) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("retrieval exceeded 4 MB response limit")
        headers = dict(response.headers)
        # iter_bytes() already decompresses; copying content-encoding would decode twice.
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=bytes(body),
            request=response.request,
        )


def _evidence(item: dict[str, Any]) -> Evidence:
    url = str(item.get("url", ""))
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username:
        raise ValueError("reference URL must be public HTTP(S) without credentials")
    fields = {
        "title": str(item.get("title", "")),
        "url": url,
        "excerpt": str(item.get("excerpt", item.get("abstract", ""))),
        "abstract": str(item.get("abstract", item.get("excerpt", ""))),
        "provider": str(item.get("provider", "supplied")),
        "identifiers": item.get("identifiers", {}),
        "published_at": str(item.get("published_at", "")),
        "full_text": str(item.get("full_text", "")),
        "full_text_url": str(item.get("full_text_url", "")),
        "retrieval": item.get("retrieval", {}),
    }
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    # ID includes content: later retrievals cannot silently replace earlier evidence.
    return Evidence(
        id=digest[:16], content_hash=digest, retrieved_at=datetime.now(UTC).isoformat(), **fields
    )


@dataclass
class ProviderResult:
    papers: list[Evidence] = field(default_factory=list)
    total: int | None = None
    raw_response: str = ""
    endpoint: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


class PaperProvider(Protocol):
    name: str

    def search(self, query: str, count: int, cutoff: str) -> ProviderResult: ...


class CrossrefProvider:
    name = "crossref"

    def __init__(self, timeout: float = 30, endpoint: str = "https://api.crossref.org/works"):
        if endpoint != "https://api.crossref.org/works":
            raise ValueError("Crossref adapter requires https://api.crossref.org/works")
        self.timeout, self.endpoint = timeout, endpoint

    def search(self, query: str, count: int, cutoff: str) -> ProviderResult:
        params: dict[str, Any] = {"query.bibliographic": query[:1000], "rows": min(count, 1000)}
        if cutoff:
            params["filter"] = f"until-pub-date:{cutoff}"
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            response = _get(client, self.endpoint, params=params)
        message = response.json()["message"]
        papers = []
        for item in message["items"]:
            abstract = plain_text(item.get("abstract", ""))
            dates = item.get("published", item.get("issued", {})).get("date-parts", [[]])
            papers.append(
                _evidence(
                    {
                        "title": " ".join(item.get("title", [])),
                        "url": item.get("URL", ""),
                        "abstract": abstract,
                        "provider": self.name,
                        "identifiers": {"doi": str(item.get("DOI", "")).lower()},
                        "published_at": _date(dates[0]),
                        "retrieval": {
                            "record": item,
                            "venue": " ".join(item.get("container-title", [])),
                            "content_level": "abstract" if abstract else "metadata",
                        },
                    }
                )
            )
        return ProviderResult(
            papers, message.get("total-results"), response.text, self.endpoint, params
        )


class SemanticScholarProvider:
    name = "semantic_scholar"
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, timeout: float = 30, api_key_env: str = "SEMANTIC_SCHOLAR_API_KEY"):
        self.timeout, self.api_key_env = timeout, api_key_env

    def search(self, query: str, count: int, cutoff: str) -> ProviderResult:
        params: dict[str, Any] = {
            "query": query[:1000],
            "limit": min(count, 100),
            "fields": "title,abstract,url,externalIds,publicationDate,year,venue,authors,openAccessPdf",
        }
        if cutoff:
            params["publicationDateOrYear"] = f":{cutoff}"
        key = os.environ.get(self.api_key_env, "")
        headers = {"x-api-key": key} if key else {}
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            response = _get(client, self.endpoint, params=params, headers=headers)
        data = response.json()
        papers = []
        for item in data["data"]:
            ids = {k.lower(): str(v) for k, v in (item.get("externalIds") or {}).items()}
            abstract = item.get("abstract") or ""
            papers.append(
                _evidence(
                    {
                        "title": item["title"],
                        "url": item.get("url")
                        or f"https://www.semanticscholar.org/paper/{item['paperId']}",
                        "provider": self.name,
                        "identifiers": ids,
                        "abstract": abstract,
                        "published_at": item.get("publicationDate")
                        or (_date([item["year"]]) if item.get("year") else ""),
                        "retrieval": {
                            "record": item,
                            "venue": item.get("venue", ""),
                            "content_level": "abstract" if abstract else "metadata",
                            "open_access_pdf": (item.get("openAccessPdf") or {}).get("url", ""),
                        },
                    }
                )
            )
        return ProviderResult(papers, data.get("total"), response.text, self.endpoint, params)


class ArxivProvider:
    name = "arxiv"
    endpoint = "https://export.arxiv.org/api/query"

    def __init__(self, timeout: float = 30):
        self.timeout = timeout

    def search(self, query: str, count: int, cutoff: str) -> ProviderResult:
        # Free-text queries must not inject arXiv query-language operators.
        words = re.findall(r"[\w-]+", query, flags=re.UNICODE)[:30]
        expression = " AND ".join(f"all:{word}" for word in words)
        if cutoff:
            expression += f" AND submittedDate:[000001010000 TO {cutoff.replace('-', '')}2359]"
        params = {"search_query": expression, "max_results": min(count, 100), "sortBy": "relevance"}
        global ARXIV_LAST_REQUEST
        with ARXIV_LOCK:
            delay = 3 - (time.monotonic() - ARXIV_LAST_REQUEST)
            if delay > 0:
                time.sleep(delay)
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                    response = _get(client, self.endpoint, params=params)
            finally:
                ARXIV_LAST_REQUEST = time.monotonic()
        if "<!DOCTYPE" in response.text.upper() or "<!ENTITY" in response.text.upper():
            raise ValueError("unsafe XML declaration in arXiv response")
        root = ET.fromstring(response.text)  # noqa: S314 - DTD/entities rejected above.
        ns = {"a": "http://www.w3.org/2005/Atom", "o": "http://a9.com/-/spec/opensearch/1.1/"}
        papers = []
        for item in root.findall("a:entry", ns):
            url = item.findtext("a:id", "", ns).replace("http://", "https://", 1)
            if "arxiv.org/api/errors" in url:
                raise ValueError("arXiv rejected the search query")
            arxiv_id = url.split("/abs/")[-1]
            abstract = item.findtext("a:summary", "", ns).strip()
            papers.append(
                _evidence(
                    {
                        "title": " ".join(item.findtext("a:title", "", ns).split()),
                        "url": url,
                        "abstract": abstract,
                        "provider": self.name,
                        "identifiers": {"arxiv": arxiv_id},
                        "published_at": item.findtext("a:published", "", ns)[:10],
                        "retrieval": {
                            "record": ET.tostring(item, encoding="unicode"),
                            "venue": "arXiv",
                            "updated_at": item.findtext("a:updated", "", ns)[:10],
                            "content_level": "abstract",
                        },
                    }
                )
            )
        total = root.findtext("o:totalResults", "", ns)
        return ProviderResult(
            papers, int(total) if total else None, response.text, self.endpoint, params
        )


def _aliases(evidence: Evidence) -> set[str]:
    identifiers = {key.lower(): value.lower() for key, value in evidence.identifiers.items()}
    aliases = {"url:" + evidence.url.rstrip("/").lower().replace("http://", "https://")}
    for key in ("doi", "arxiv"):
        if identifiers.get(key):
            value = identifiers[key]
            if key == "arxiv":
                value = re.sub(r"v\d+$", "", value)
            aliases.add(f"{key}:{value}")
    return aliases


def _unique_papers(evidence: list[Evidence]) -> list[Evidence]:
    """Join papers through any shared DOI/arXiv identity, including bridge records."""
    groups: list[tuple[set[str], list[Evidence]]] = []
    for item in evidence:
        aliases, members = _aliases(item), [item]
        separate = []
        for known, papers in groups:
            if known & aliases:
                aliases.update(known)
                members.extend(papers)
            else:
                separate.append((known, papers))
        groups = [*separate, (aliases, members)]
    return [
        max(papers, key=lambda item: (len(item.full_text), len(item.abstract)))
        for _, papers in groups
    ]


class Literature:
    def __init__(self, config: ResearchConfig, providers: list[PaperProvider] | None = None):
        self.config = config
        options = config.literature
        available: dict[str, PaperProvider] = {
            "crossref": CrossrefProvider(options.timeout_seconds, config.search_endpoint),
            "semantic_scholar": SemanticScholarProvider(
                options.timeout_seconds, options.semantic_scholar_api_key_env
            ),
            "arxiv": ArxivProvider(options.timeout_seconds),
        }
        self.providers = (
            providers if providers is not None else [available[name] for name in options.providers]
        )
        self.search_history: list[dict[str, Any]] = []
        self.last_report: dict[str, Any] = {}
        self._cache: dict[tuple[str, int, str], list[Evidence]] = {}
        self._lock = threading.RLock()
        self.publication_cutoff = options.publication_cutoff

    def search(self, query: str, count: int = 40) -> list[Evidence]:
        found = [self._evidence(item) for item in self.config.references]
        external = self.search_external(query, count)
        if self.publication_cutoff:
            found = [
                e for e in found if e.published_at and e.published_at <= self.publication_cutoff
            ]
        return _unique_papers([*found, *external])

    def search_external(self, query: str, count: int = 40) -> list[Evidence]:
        """Search independent providers; returned supplied corpus is never self-verification."""
        with self._lock:
            return self._search_external(query, count)

    def _search_external(self, query: str, count: int) -> list[Evidence]:
        cutoff = self.publication_cutoff
        if cutoff:
            date.fromisoformat(cutoff)
        options = self.config.literature
        limit = min(count, options.max_results)
        if limit < 1 or not query.strip():
            raise ValueError("literature search requires a query and positive limit")
        report: dict[str, Any] = {
            "query": query,
            "cutoff": cutoff,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "limit": limit,
            "results_per_provider": options.results_per_provider,
            "providers": [],
            "evidence_ids": [],
            "excluded": [],
            "limitations": [],
            "exhaustive": False,
        }
        self.last_report = report
        self.search_history.append(report)
        if not self.config.search_enabled:
            report["limitations"].append(
                "external search disabled; novelty and independent citation verification are unverified"
            )
            return []
        cache_key = (query, limit, cutoff)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            report.update({"cached": True, "evidence_ids": [e.id for e in cached]})
            report["limitations"].append(
                "cached bounded search; see original report for provider failures"
            )
            return cached
        candidates: list[Evidence] = []
        for provider in self.providers:
            detail: dict[str, Any] = {"provider": provider.name, "status": "failed"}
            report["providers"].append(detail)
            try:
                response = provider.search(query, min(limit, options.results_per_provider), cutoff)
                detail.update(
                    {
                        "status": "completed",
                        "returned": len(response.papers),
                        "total": response.total,
                        "endpoint": response.endpoint,
                        "parameters": response.parameters,
                        "raw_response": response.raw_response,
                        "response_sha256": hashlib.sha256(
                            response.raw_response.encode()
                        ).hexdigest(),
                    }
                )
                if response.total is None or response.total > len(response.papers):
                    report["limitations"].append(
                        f"{provider.name}: bounded first-page search; more or unknown total results"
                    )
                for evidence in response.papers:
                    reason = ""
                    if cutoff and (not evidence.published_at or evidence.published_at > cutoff):
                        reason = (
                            "missing publication date"
                            if not evidence.published_at
                            else "after publication cutoff"
                        )
                    # A post-cutoff revision can change abstracts as well as full text.
                    if cutoff and evidence.retrieval.get("updated_at", "") > cutoff:
                        reason = "retrieved revision updated after publication cutoff"
                    if reason:
                        report["excluded"].append(
                            {"reason": reason, "evidence": evidence.model_dump()}
                        )
                        continue
                    candidates.append(evidence)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, ET.ParseError) as error:
                # Never persist request headers or credentials in exception messages.
                detail["error"] = type(error).__name__
                if isinstance(error, httpx.HTTPStatusError):
                    detail["http_status"] = error.response.status_code
                report["limitations"].append(
                    f"{provider.name}: retrieval failed ({detail['error']})"
                )
        unique = _unique_papers(candidates)
        papers = unique[:limit]
        if len(unique) > limit:
            report["limitations"].append("merged results truncated to configured max_results")
        if options.full_text:
            for index, paper in enumerate(papers[: options.max_full_text_papers]):
                papers[index] = self.inspect(paper)
        report["evidence_ids"] = [e.id for e in papers]
        report["content_counts"] = {
            level: sum(bool(getattr(e, level)) for e in papers)
            for level in ("abstract", "full_text")
        }
        if len(papers) < 3:
            report["limitations"].append(
                "fewer than three independent references: insufficient for a novelty conclusion"
            )
        if not any(e.abstract or e.full_text for e in papers):
            report["limitations"].append(
                "no inspectable abstract/full text; metadata alone cannot support novelty"
            )
        self._cache[cache_key] = papers
        return papers

    def inspect(self, evidence: Evidence) -> Evidence:
        """Retrieve arXiv HTML full text only; no model-controlled arbitrary URL fetching."""
        data = evidence.model_dump()
        retrieval = dict(evidence.retrieval)
        arxiv_id = evidence.identifiers.get("arxiv", "")
        if not arxiv_id or not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", arxiv_id):
            retrieval["full_text_status"] = "unavailable: no supported open full-text identifier"
        elif self.publication_cutoff and not re.search(r"v\d+$", arxiv_id):
            retrieval["full_text_status"] = (
                "unverified: unversioned full text excluded under publication cutoff"
            )
        else:
            url = f"https://arxiv.org/html/{arxiv_id}"
            try:
                with httpx.Client(
                    timeout=self.config.literature.timeout_seconds, follow_redirects=False
                ) as client:
                    response = _get(client, url)
                text = plain_text(response.text)
                if len(text) < 500:
                    raise ValueError("full text unavailable or too short")
                maximum = self.config.literature.max_full_text_chars
                data.update(full_text=text[:maximum], full_text_url=url)
                retrieval.update(
                    full_text_status="retrieved",
                    full_text_sha256=hashlib.sha256(response.content).hexdigest(),
                    full_text_truncated=len(text) > maximum,
                    full_text_original_chars=len(text),
                    content_level="full_text",
                )
            except (httpx.HTTPError, ValueError) as error:
                retrieval["full_text_status"] = f"unavailable: {type(error).__name__}"
        data["retrieval"] = retrieval
        return _evidence(data)

    @staticmethod
    def _evidence(item: dict[str, Any]) -> Evidence:
        return _evidence(item)


def novelty_coverage(
    evidence: list[Evidence], reports: list[dict[str, Any]], minimum: int = 3
) -> dict[str, Any]:
    """A minimum evidence gate, explicitly not a claim of exhaustive novelty search."""
    external = [e for e in evidence if e.provider != "supplied"]
    substantive = [e for e in external if e.abstract or e.full_text or e.excerpt]
    errors = [
        p
        for report in reports
        for p in report.get("providers", [])
        if p.get("status") != "completed"
    ]
    return {
        "sufficient_for_assessment": len(_unique_papers(substantive)) >= minimum and bool(reports),
        "independent_papers": len(_unique_papers(external)),
        "inspectable_papers": len(_unique_papers(substantive)),
        "provider_failures": errors,
        "exhaustive": False,
        "limits": [item for report in reports for item in report.get("limitations", [])],
    }
