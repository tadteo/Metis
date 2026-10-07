# Bound evidence full text in agent prompts

Base: `54df93a`. Branch: `codex/bound-evidence-full-text`. Status: complete on task branch; not merged.

## Source requirement

Live run `bb0cb916c8e7` (2026-10-07) sent a 1,408,443-character novelty request
(event seq 2089, call `9e71d102…`). `state.evidence` held 39 records; 18 carried
retrieved full text (raw 18,617–80,000 characters each, 1,116,683 raw characters in
total; abstracts 44,950). The literature bound (`max_full_text_chars=80000`,
`max_full_text_papers=8`) applies per search, while evidence accumulates across the
limitation and novelty searches. The request could never pass a 250k tokens/minute
free-tier quota and each attempt reserved a conservative cost of about USD 9.95.
Earlier limitations/verify/generate requests in the same run were 154–157k
characters with two records, 127,315 of them full text.

## Root cause

[Bounded evidence context](bounded-evidence-context.md) intentionally bounded only
bibliographic metadata (title, venue) and transport records. Its module contract
and `test_projection_preserves_arbitrary_science_and_full_passages` required
`abstract`, `excerpt` and `full_text` to pass through unchanged, and no per-request
evidence budget existed. Every role serialized the whole `state.evidence`, so no
role bypassed the projection: the projection itself never bounded passages.

## Boundary

- `evidence_context.retrieval_model_view` bounds passages of recognized Evidence
  records only. Arbitrary scientific dictionaries, experiments and history records
  keep their content. Stored `RunState.evidence`, artifacts and integrity/novelty
  gates keep the complete records.
- Per item: abstract ≤ 3,000 characters, separate excerpt ≤ 2,000, full text ≤ 6,000
  as focus-ranked 1,000-character windows. Per request: at most 80,000 passage
  characters across unique records. Priority evidence (linked to the active ideas or
  listed under evidence-citing keys in stage context) reserves up to half the budget
  for full text; abstracts share the rest (shrunk evenly only if needed); remaining
  full-text room goes to priority records, then by overlap with the stage focus.
- Every record keeps its ID, hash, URL and metadata, so all evidence remains citable.
  `model_view.omissions` records original/shown size, SHA-256 and selected windows.
- `AgentRunner` records an `evidence_view` provenance summary on `agent_started`.
- Shared prompt guidance (`common.md`) states that passages may be bounded excerpts;
  every agent version and the catalog version increase.

## Acceptance

- Regression reproducing the live shape (39 records, ~34k-character full texts)
  yields novelty, limitations and generate_ideas requests below 200,000 characters.
- Truncation provenance recorded per call; gates still see full stored evidence.
- Existing suites, static checks, spec validation, browser tests, wheel, scanner, demo.

## Implemented and observed

Commits: `37f8ae2` (feature), `489314d` (review fixes), then this documentation commit.
The failing contract was explicit: `test_projection_preserves_arbitrary_science_and_full_passages`
asserted unchanged full text; it is replaced by a bounded-passage test.

Synthetic regression (39 records, 34,500-character full texts, 1.32M JSON characters),
measured through `AgentRunner` with the default provider prices:

| Role | Prompt chars before → after | Request bound bytes before → after | Reservation USD before → after |
|---|---|---|---|
| novelty | 1,404,413 → 101,825 | 1,409,805 → 107,532 | 17.3497 → 1.7224 |
| limitations | 1,405,640 → 103,052 | 1,410,920 → 108,647 | 17.3630 → 1.7358 |
| generate_ideas | 1,404,402 → 101,814 | 1,409,740 → 107,467 | 17.3489 → 1.7216 |

"Before" ran the same script against the `main` checkout source (`54df93a`). The
tests assert < 200,000 prompt characters and < 250,000 request-bound bytes.

Offline replay of the stored live contexts (read-only private Store; counts only, in
[the replay summary](../evidence/bound-evidence-full-text-replay.json)): novelty
1,408,443 → 125,900 characters (reservation USD 9.948 → about 1.29 under the run's
exact linear rule); limitations 156,510 → 20,717 (USD 1.496 → about 0.58);
generate_ideas 155,553 → 19,695 (USD 1.489 → about 0.57). Novelty passages shown:
74,559 of 1,161,633 characters; all 39 IDs present. The replay uses each stored
request's original system prompt. No model call was made; this is not evidence that
the run will now pass the novelty stage or the free-tier quota.

## Validation

- Focused: `tests/test_evidence_context.py`, `tests/test_agents.py`, `tests/test_literature.py`,
  `tests/test_review.py`, `tests/test_review_persistence.py`, `tests/test_coding.py`: 116 passed.
- Full `uv run --no-sync python -m pytest -q`: 1,160 passed, 4 skipped (after `37f8ae2`);
  1,163 passed, 4 skipped in 366 s (after `489314d`).
- `ruff format .`, `ruff check .`, `mypy src` (87 files), `metis validate-specs`
  (48 agents, 29 stages, valid), `node --test tests/*_ui.mjs` (107 passed),
  `scripts/scan_secrets.py` (passed), `uv build --wheel` +
  `AUTORESEARCH_TEST_WHEEL=dist pytest tests/test_package.py` (1 passed), `metis demo` (completed),
  `tests/test_fidelity_matrix.py` (17 passed).
- Independent review: [record](../reviews/bound-evidence-full-text.md); approve after fixes.

## Open risks

- Review panels (`review.py`) project without a focus, so they see leading excerpts.
- Citation entailment and method alignment now see bounded passages; claim-cited
  evidence is prioritized, but support outside the selected windows is invisible.
- Intake previously saw supplied documents (up to 500k characters) in full; it now
  sees bounded windows.
- Focus-dependent windows change evidence chunks between calls, reducing provider
  prompt-cache reuse.
- Metadata still scales with record count (~700 characters/record); the budget bounds
  passages, not the record count. Laya typed advice uses its own transport.
- Constants are module-level, not configuration.
