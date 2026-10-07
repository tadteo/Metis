# Novelty retrieval queries

Base: `4eb8c56` (`main`). Branch: `codex/novelty-retrieval-queries`.
Owned files: `src/autoresearch/literature.py`, `src/autoresearch/research_stages/seeds.py`,
`src/autoresearch/paper_orchestra_worker.py` (shared backoff only), `tests/test_literature.py`,
this plan, and the retrieval rows of `docs/paper-spec.md`/`docs/fidelity.md`.

## Source requirement (live evidence)

Private run `c949e49b233c` (2026-10-07 19:37 UTC, novelty artifact
`novelty-idea_poly_reg_tradeoff-v3.json`, kept in private state). Redacted summary:

- The novelty stage sent one 364-character query (idea title + hypothesis sentence).
- arXiv received about 30 `all:` terms joined by `AND`, including stopwords (`with`, `the`,
  `will`) and code tokens (`py`): 0 results, total 0.
- Crossref `query.bibliographic` with the full sentence returned 2 off-topic records
  (total 62), metadata only.
- Semantic Scholar (keyless) answered HTTP 429; the main pipeline did not retry.
- `limit` was 2 because the fetch count equalled `pipeline.novelty_references` (2).
- The gate correctly stopped with "novelty requires inspectable paper content, not metadata alone".

## Boundary

Retrieval mechanics only: provider query construction, fetch count and transient-failure
backoff. No gate, minimum, coverage rule or scientific contract changes. Prompt-size bounds
from `bounded-evidence-context.md` must hold.

## Acceptance criteria

1. Built-in providers derive a bounded keyword query (stopwords, punctuation, code/path tokens
   and number-only tokens dropped; at most 8 salient terms; hyphenated compounds kept as
   phrases). arXiv uses a few required core terms plus an optional `OR` group instead of
   AND-ing every token. The search report keeps the raw query and each provider's derived query,
   including for failed providers.
2. Novelty search fetches `max(novelty_references, results_per_provider)` per query, still
   bounded by `literature.max_results`; `novelty_references` stays the minimum.
3. HTTP 429/5xx and transport errors get bounded retries (3 attempts, Retry-After honoured,
   each wait capped at 60 s), recorded per provider. The writer worker uses the same policy.
4. Regression tests: the live arXiv query is bounded; stopword/code-token removal; fetch count
   above the minimum; S2 429 then success with a fake transport and fake sleep; provenance
   holds both queries; existing literature/writer tests stay green.

## Implementation and validation

(recorded below as work proceeds)
