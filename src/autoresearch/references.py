"""Citation provenance checks with independent metadata re-retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from .contracts import Evidence
from .literature import Literature


def normalized_url(url: str) -> str:
    return (
        unquote(url)
        .lower()
        .replace("http://", "https://")
        .replace("https://dx.doi.org/", "https://doi.org/")
        .rstrip("/.,")
    )


@dataclass
class CitationAudit:
    verified: list[str]
    issues: list[str]


def audit_references(
    manuscript: str, evidence: list[Evidence], literature: Literature
) -> CitationAudit:
    known = {normalized_url(e.url): e for e in evidence}
    cited = {normalized_url(url) for url in re.findall(r"https?://[^\s)\]>]+", manuscript)}
    ids = re.findall(r"\[@([A-Za-z0-9_-]+)\]", manuscript)
    by_id = {e.id: e for e in evidence}
    issues = [f"Unknown citation ID: {eid}" for eid in ids if eid not in by_id]
    cited.update(normalized_url(by_id[eid].url) for eid in ids if eid in by_id)
    if not cited:
        issues.append(
            "Manuscript has no machine-verifiable citations; use evidence URLs or [@evidence_id]."
        )
    verified = []
    for url in sorted(cited):
        if url not in known:
            issues.append(f"Citation not grounded in retrieved evidence: {url}")
            continue
        reference = known[url]
        # Fresh primary metadata retrieval, not an LLM assertion of existence.
        # Ordinary search also includes the operator's corpus. That corpus is
        # evidence to investigate, never independent confirmation of itself.
        results = literature.search_external(reference.title, 5)
        if any(normalized_url(item.url) == url for item in results):
            verified.append(reference.id)
        else:
            issues.append(f"Citation could not be independently re-retrieved: {reference.id}")
    return CitationAudit(verified, issues)
