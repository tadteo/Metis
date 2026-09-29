"""Markdown/LaTeX citation provenance checks with independent re-retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from .contracts import Evidence
from .literature import Literature


def normalized_url(url: str) -> str:
    return (
        unquote(url)
        .replace("\\_", "_")
        .replace("\\&", "&")
        .lower()
        .replace("http://", "https://")
        .replace("https://dx.doi.org/", "https://doi.org/")
        .rstrip("/.,}")
    )


def _same_source(left: Evidence, right: Evidence) -> bool:
    if normalized_url(left.url) == normalized_url(right.url):
        return True
    a = {k.lower(): v.lower() for k, v in left.identifiers.items()}
    b = {k.lower(): v.lower() for k, v in right.identifiers.items()}
    # BibTeX keys are local labels, never independent bibliographic identities.
    return any(
        a.get(key) and a[key] == b.get(key)
        for key in ("doi", "arxiv", "corpusid", "pubmed", "dblp")
    )


@dataclass
class CitationAudit:
    verified: list[str]
    issues: list[str]


def _without_latex_comments(manuscript: str) -> str:
    lines = []
    for line in manuscript.splitlines(keepends=True):
        for match in re.finditer(r"(\\*)%", line):
            if len(match.group(1)) % 2 == 0:
                line = line[: match.end() - 1] + ("\n" if line.endswith("\n") else "")
                break
        lines.append(line)
    return "".join(lines)


def audit_references(
    manuscript: str, evidence: list[Evidence], literature: Literature
) -> CitationAudit:
    # Commented citations must not make an otherwise uncited manuscript pass.
    latex = re.search(
        r"\\(?:documentclass\b|begin\s*\{document\}|cite[a-zA-Z]*\b|autocite\b|parencite\b|textcite\b)",
        manuscript,
    )
    text = _without_latex_comments(manuscript) if latex else manuscript
    known = {normalized_url(e.url): e for e in evidence}
    cited = {normalized_url(url) for url in re.findall(r"https?://[^\s)\]>}]+", text)}
    ids = set(re.findall(r"\[@([A-Za-z0-9_:.+-]+)\]", text))
    latex_keys = re.findall(
        r"\\(?:cite[a-zA-Z]*|autocite|parencite|textcite)\*?(?:\[[^\]]*\])*\{([^}]+)\}", text
    )
    ids.update(key.strip() for group in latex_keys for key in group.split(",") if key.strip())
    by_id = {e.id: e for e in evidence}
    ambiguous = set()
    for item in evidence:
        key = item.identifiers.get("bibtex", "")
        if key:
            if key in by_id and not _same_source(by_id[key], item):
                ambiguous.add(key)
            by_id[key] = item
    issues = [f"Ambiguous BibTeX citation key: {key}" for key in sorted(ids & ambiguous)]
    issues.extend(f"Unknown citation ID: {eid}" for eid in sorted(ids - set(by_id)))
    cited.update(
        normalized_url(by_id[eid].url) for eid in ids if eid in by_id and eid not in ambiguous
    )
    if not cited:
        issues.append(
            "Manuscript has no machine-verifiable citations; use evidence URLs, [@evidence_id], or retrieved BibTeX keys."
        )
    verified = []
    for url in sorted(cited):
        if url not in known:
            issues.append(f"Citation not grounded in retrieved evidence: {url}")
            continue
        reference = known[url]
        # search_external excludes supplied corpus; a URL or BibTeX key is not evidence.
        results = literature.search_external(reference.title, 5)
        if any(_same_source(reference, item) for item in results):
            verified.append(reference.id)
        else:
            issues.append(f"Citation could not be independently re-retrieved: {reference.id}")
    return CitationAudit(verified, issues)
