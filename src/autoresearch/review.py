"""ScholarPeer reconstruction driven by the published, attributed Appendix G prompts.

The original templates remain byte-for-byte assets. This module implements their
retrieval/cutoff contracts and adapts their output formats to the runtime schema.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .catalog import load_catalog
from .contracts import AgentOutput, Evidence, RunState
from .literature import Literature, novelty_coverage

ASSETS = Path(__file__).parent / "assets" / "scholarpeer"
PROMPT_MANIFEST = json.loads((ASSETS / "manifest.json").read_text())


def load_published_prompt(role: str) -> str:
    entry = PROMPT_MANIFEST["prompts"][role]
    content = (ASSETS / str(entry["file"])).read_text()
    if hashlib.sha256(content.encode()).hexdigest() != entry["sha256"]:
        raise ValueError(f"published ScholarPeer prompt hash mismatch: {role}")
    return content


ADAPTATION = load_catalog().text("prompts/review_adaptation.md")
# Published source assets remain byte-for-byte; runtime composition lives in the catalog.

VENUES: dict[str, dict[str, Any]] = {
    "ICLR": {
        "name": "ICLR 2025",
        "source": "https://iclr.cc/Conferences/2025/ReviewerGuide",
        "scale": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "dimensions": ["soundness", "presentation", "contribution"],
        "sections": [
            "summary",
            "strengths",
            "weaknesses",
            "questions",
            "limitations",
            "rating",
            "confidence",
        ],
        "anchors": {
            "1": "strong rejection",
            "3": "reject",
            "5": "borderline reject",
            "6": "borderline accept",
            "8": "strong accept",
            "10": "award quality",
        },
    },
    "NEURIPS": {
        "name": "NeurIPS 2025",
        "source": "https://neurips.cc/Conferences/2025/ReviewerGuidelines",
        "scale": [1, 2, 3, 4, 5, 6],
        "dimensions": ["quality", "clarity", "significance", "originality"],
        "sections": [
            "summary",
            "strengths",
            "weaknesses",
            "questions",
            "limitations",
            "rating",
            "confidence",
        ],
        "anchors": {
            "1": "strong reject",
            "2": "reject",
            "3": "borderline reject",
            "4": "borderline accept",
            "5": "accept",
            "6": "strong accept",
        },
    },
}


def render_published_prompt(role: str, values: dict[str, Any]) -> str:
    """Only substitute named placeholders; literal JSON braces remain untouched."""
    template = load_published_prompt(role)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise ValueError(f"missing ScholarPeer template variable: {key}")
        value = values[key]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return (
        re.sub(r"(?<!\{)\{([a-z_]+)\}(?!\})", replace, template)
        .replace("{{", "{")
        .replace("}}", "}")
    )


def eligible_review_source(evidence: Evidence) -> bool:
    """Published §3.1 quality filter: arXiv and relevant top-tier proceedings."""
    host = urlparse(evidence.url).hostname or ""
    allowed = {
        "arxiv.org",
        "aclanthology.org",
        "proceedings.mlr.press",
        "papers.nips.cc",
        "papers.neurips.cc",
        "proceedings.neurips.cc",
        "openaccess.thecvf.com",
        "openreview.net",
    }
    if host in allowed or "arxiv" in evidence.identifiers:
        return True
    venue = str(evidence.retrieval.get("venue", ""))
    return bool(
        re.search(
            r"\b(?:NeurIPS|NIPS|ICLR|ICML|CVPR|ICCV|ECCV|ACL|EMNLP|NAACL|AAAI|IJCAI|KDD|SIGIR|WWW|COLT|AISTATS|UAI|ICRA|IROS|RSS)\b|International Conference on Machine Learning|Neural Information Processing Systems|Computer Vision and Pattern Recognition",
            venue,
            re.I,
        )
    )


def _questions(output: AgentOutput, expected: int, role: str) -> list[str]:
    questions = [plan.get("question") for plan in output.plans]
    if len(questions) != expected or any(
        not isinstance(q, str) or not q.strip() for q in questions
    ):
        raise ValueError(f"{role} must return exactly {expected} nonempty question plans")
    return [str(q).strip() for q in questions]


def retrieval_model_view(value: Any) -> Any:
    """Omit duplicate transport records, retaining all inspected content and coverage.

    Exact raw records stay in review_context's immutable artifact. This changes
    payload representation, not the evidence available to scientific agents.
    """
    if isinstance(value, dict):
        return {
            key: retrieval_model_view(item)
            for key, item in value.items()
            if key not in {"raw_response", "record", "raw_source"}
            and not (key == "excerpt" and item == value.get("abstract"))
        }
    if isinstance(value, list):
        return [retrieval_model_view(item) for item in value]
    return value


def _validate_step(role: str, result: AgentOutput, evidence: set[str], questions: int) -> None:
    if not result.summary.strip():
        raise ValueError("ScholarPeer output requires a substantive summary")
    if role == "review_summary" and not {"claims", "method", "evidence"} <= set(result.structured):
        raise ValueError("ScholarPeer structured extraction requires claims, method and evidence")
    if role.endswith("questions"):
        _questions(result, questions, role)
    if role == "review_novelty_answers" and evidence and not result.evidence_ids:
        raise ValueError("ScholarPeer novelty answer must cite retrieved evidence IDs")
    if role.endswith("answers") and set(result.evidence_ids) - evidence:
        raise ValueError("ScholarPeer answer cites an unretrieved or excluded evidence ID")


def review_context(
    state: RunState,
    call: Callable[[str, dict[str, Any]], AgentOutput],
    literature: Literature,
    parallelism: int,
    adaptation: str | None = None,
) -> dict[str, Any]:
    config = literature.config.scholarpeer
    venue = VENUES[config.venue.upper()]
    cutoff = (
        config.publication_cutoff
        or literature.publication_cutoff
        or state.created_at[:10]
        or datetime.now(UTC).date().isoformat()
    )
    literature.publication_cutoff = cutoff
    outputs: list[dict[str, Any]] = []
    references: dict[str, Evidence] = {}
    source_exclusions: list[dict[str, Any]] = []
    query_count = 0
    limits: list[str] = []
    values: dict[str, Any] = {
        "paper_text": state.manuscript,
        "paper_abstract": state.title + "\n" + state.manuscript,
        "cutoff_date": cutoff,
        "review_guidelines": venue,
        "fewshot_examples": "",
        "num_questions": config.qa_pairs_per_criterion,
        "aspect": "technical soundness",
    }

    def invoke(role: str, context: dict[str, Any], **variables: Any) -> AgentOutput:
        rendered = render_published_prompt(role, retrieval_model_view({**values, **variables}))
        repairs = literature.config.pipeline.max_agent_repairs
        has_frontier = literature.config.frontier_provider is not None
        last_error = ""
        for attempt in range(repairs + 1 + int(has_frontier)):
            request_context = {
                **retrieval_model_view(context),
                "published_prompt": rendered,
                "publication_cutoff": cutoff,
                "prompt_source": PROMPT_MANIFEST["prompts"][role],
                "runtime_adaptation": adaptation or ADAPTATION,
                "transport_records": "Exact raw responses and records retained in the review artifact; all inspected abstract/full text remains supplied.",
            }
            if attempt:
                request_context.update(quality_repair=last_error, quality_attempt=attempt)
            if attempt > repairs:
                request_context.update(escalate=True, escalation_reason=last_error)
            result = call(role, request_context)
            record = {
                "role": role,
                "output": result.model_dump(),
                "attempt": attempt,
                "prompt_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                "question": variables.get("question", ""),
                "escalated": attempt > repairs,
            }
            outputs.append(record)
            try:
                _validate_step(role, result, set(references), config.qa_pairs_per_criterion)
            except ValueError as error:
                last_error = str(error)
                record["validation_error"] = last_error
                continue
            return result
        raise ValueError(f"{role}: {last_error}; semantic repair budget exhausted")

    def retrieve(query: str) -> list[Evidence]:
        nonlocal query_count
        if query_count >= config.max_search_queries:
            limits.append(f"search-query ceiling reached; unexecuted query: {query}")
            return []
        query_count += 1
        selected = []
        for item in literature.search(query, literature.config.literature.max_results):
            if not item.published_at or item.published_at > cutoff:
                source_exclusions.append(
                    {"evidence": item.model_dump(), "reason": "missing date or after cutoff"}
                )
            elif eligible_review_source(item):
                references[item.id] = item
                selected.append(item)
            else:
                source_exclusions.append(
                    {
                        "evidence": item.model_dump(),
                        "reason": "venue not verified as eligible top-tier proceedings or arXiv",
                    }
                )
        return selected

    summary = invoke(
        "review_summary",
        {
            "structured_extraction_fields": [
                "claims",
                "method",
                "evidence",
                "datasets",
                "metrics",
                "baselines",
                "limitations",
            ]
        },
    )
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", state.manuscript, re.S)
    values["paper_abstract"] = (
        state.title + "\n" + (abstract.group(1) if abstract else summary.summary)
    )
    initial = retrieve(state.title + " " + summary.summary[:500])
    review = invoke(
        "review_literature",
        {
            "summary": summary.model_dump(),
            "retrieved": [e.model_dump() for e in initial],
            "search_reports": literature.search_history,
        },
    )
    initial_review = review.model_dump()
    domain_analysis = review.structured.get("domain_analysis", {})
    extracted_references = list(review.structured.get("references", []))
    expansion_outputs = []
    for iteration in range(config.literature_rounds):
        plans = review.plans
        fallback = [
            "foundational methods and datasets",
            "direct competing methods and state of the art",
            "recent preprints and concurrent work",
        ]
        queries = [
            str(p["question"])
            for p in plans
            if isinstance(p.get("question"), str) and p["question"].strip()
        ]
        if not queries:
            queries = [state.title + " " + fallback[iteration % len(fallback)]]
        for query in queries:
            retrieve(query)
        review = invoke(
            "review_expansion",
            {
                "round": iteration + 1,
                "retrieved": [e.model_dump() for e in references.values()],
                "previous_review": review.model_dump(),
                "search_reports": literature.search_history,
            },
            current_references_json={
                "domain_analysis": domain_analysis,
                "references": extracted_references,
            },
        )
        expansion_outputs.append(review.model_dump())
        extracted_references.extend(review.structured.get("references", []))
    literature_ledger = {
        "domain_analysis": domain_analysis,
        "references": extracted_references,
        "initial": initial_review,
        "expansions": expansion_outputs,
    }
    scout_refs = retrieve(
        state.title
        + " "
        + json.dumps(summary.structured.get("datasets", []))
        + " benchmark state of the art baselines"
    )
    with ThreadPoolExecutor(max_workers=max(1, min(2, parallelism))) as pool:
        historian_future = pool.submit(
            invoke,
            "review_historian",
            {"retrieved": [e.model_dump() for e in references.values()]},
            literature_review_json=literature_ledger,
        )
        scout_future = pool.submit(
            invoke,
            "review_baseline_scout",
            {"summary": summary.model_dump(), "retrieved": [e.model_dump() for e in scout_refs]},
        )
        historian, scout = historian_future.result(), scout_future.result()
    values.update(
        summary=summary.summary,
        domain_narrative=historian.summary,
        literature_review=literature_ledger,
        missing_baselines_datasets=scout.structured or scout.model_dump(),
    )
    context = {
        "summary": summary.model_dump(),
        "literature": literature_ledger,
        "expansion_rounds": expansion_outputs,
        "historian": historian.model_dump(),
        "baseline_scout": scout.model_dump(),
    }
    qa: dict[str, Any] = {}
    pairs = []
    for aspect in ("novelty", "technical"):
        questions = invoke(f"review_{aspect}_questions", context)
        question_texts = _questions(questions, config.qa_pairs_per_criterion, aspect)
        answers = []
        for index, question in enumerate(question_texts):
            answer_context: dict[str, Any] = {
                **context,
                "question_index": index,
                "question": question,
            }
            if aspect == "novelty":
                answer_refs = retrieve(question)
                answer_context.update(
                    retrieved=[e.model_dump() for e in answer_refs],
                    search_reports=literature.search_history,
                    coverage=novelty_coverage(list(references.values()), literature.search_history),
                )
            answer = invoke(f"review_{aspect}_answers", answer_context, question=question)
            answers.append(answer.model_dump())
            pairs.append({"aspect": aspect, "question": question, "answer": answer.model_dump()})
        qa[aspect] = {"questions": questions.model_dump(), "answers": answers}
    values["qa_pairs_text"] = pairs
    coverage = novelty_coverage(list(references.values()), literature.search_history)
    coverage["limits"].extend(limits)
    if len(references) < 30:
        coverage["limits"].append(
            "fewer than the Appendix G initial target of 30–50 eligible papers retrieved"
        )
    return {
        **context,
        "qa": qa,
        "qa_pairs": pairs,
        "review_evidence": [e.model_dump() for e in references.values()],
        "review_guidelines": venue,
        "publication_cutoff": cutoff,
        "search_reports": literature.search_history,
        "literature_coverage": coverage,
        "source_quality_exclusions": source_exclusions,
        "individual_outputs": outputs,
        "prompt_provenance": PROMPT_MANIFEST,
        "published_prompt": render_published_prompt("peer_review", values),
        "review_purpose": "improvement",
        "held_out": False,
        "score_semantics": "venue-specific simulated recommendation, never venue acceptance probability",
        "fewshot_examples_status": "not published in Appendix G; empty placeholder retained",
    }
