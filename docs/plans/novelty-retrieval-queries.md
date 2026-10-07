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

1. Built-in providers condense queries longer than 12 words to a bounded keyword query
   (stopwords, punctuation, code/path tokens and number-only tokens dropped; at most 8 salient
   terms; hyphenated compounds kept as phrases). Shorter queries (citation titles, writer task
   foci) are sent as before so title lookup is not degraded. arXiv uses a few required core terms plus an optional `OR` group instead of
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

Feature commit `aa3e471`; fidelity/documentation commit follows it.

- `literature.py`: `query_terms`, `keyword_query`, `arxiv_expression` (built-in providers expose
  `provider_query`); report fields `keyword_query` and `providers[].provider_query`; shared
  `retry_decision` and `Literature._provider_search` (3 attempts, Retry-After seconds/HTTP date,
  60 s cap, `providers[].backoff` events, injectable `Literature.sleep`). Providers wrapped by the
  writer's `ThrottledProvider` (`handles_backoff`) are not retried twice; the writer throttle now
  uses `retry_decision`.
- `seeds.py`: `novelty_fetch_count` = max(`novelty_references`, `min_novelty_sources`,
  `results_per_provider`) bounded by `max_results`. In the live configuration (2, 3, 12, 40) the
  fetch rises from 2 to 12. Default configuration (12, 3, 12, 40) is unchanged at 12, so the
  bounded-evidence-context prompt sizes for defaults are unchanged; the `two-references`
  evaluation arm (`max_results` 2) still fetches 2. No gate or minimum changed.
- Reproduction before the fix: base `ArxivProvider` on the synthetic regression sentence sent
  30 `all:` terms joined by 29 `AND`s. After: 8 terms, 3 required + optional OR group.

Tests added to `tests/test_literature.py`: stopword/code/number removal and short-query
passthrough; bounded arXiv expression (regression); Semantic Scholar 429 → success with
Retry-After 7 s and a fake sleep, both queries in provenance; bounded/capped 503 retries and no
retry for 400; engine novelty fetch 12 > minimum 2. The existing 429 test now injects the sleep and
asserts the bounded attempts.

Commands (2026-10-07, worktree `Metis-novelty-queries`):

- `uv sync --frozen --group dev --extra evaluation`: ok.
- `uv run --no-sync ruff format --check .` / `ruff check .`: pass. `mypy src`: 87 files, no issues.
- `uv run --no-sync metis validate-specs`: pass.
- `uv run --no-sync python -m pytest -q`: 1147 passed, 4 skipped (363 s). An earlier full run,
  made concurrently with the demo and browser suites and before the short-query passthrough,
  had one failure in demo-mode `tests/test_engine.py::test_failed_candidates_feed_all_rounds_and_do_not_create_paper`
  (`blocked` vs `failed`); it passed alone and in the final full run. It does not use retrieval;
  recorded as a load-sensitive flake.
- `node --test tests/*_ui.mjs`: 107 passed. `scripts/scan_secrets.py`: pass.
- `metis demo` (scratch `AUTORESEARCH_HOME`): completed, exit 0 (synthetic).
- `uv build --wheel` + `AUTORESEARCH_TEST_WHEEL=dist pytest tests/test_package.py`: 1 passed.
- `tests/test_fidelity_matrix.py` after regeneration: 17 passed.

No live network or model calls were made. Whether condensed queries retrieve relevant,
inspectable papers in a live novelty run is unmeasured; a live rerun is the next evidence step.

## Open items

- Independent review not yet performed (required before merge, record under `docs/reviews/`).
- Short queries keep the old arXiv all-terms conjunction; the third novelty query
  (`title + "alternative prior methods limitations"`) can still be too strict on arXiv.
- Salience is order-of-appearance after filtering, not TF-IDF; a long hypothesis whose title is
  generic may lead with weak core terms.
- Keyless Semantic Scholar may still 429 after three attempts; the failure is recorded and the
  gate stays strict. A key (`SEMANTIC_SCHOLAR_API_KEY`) remains supported.
