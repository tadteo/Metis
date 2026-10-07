# Independent review: novelty retrieval queries

- Reviewer: Claude (Opus 5.5), independent review agent, 2026-10-07
- Branch: `codex/novelty-retrieval-queries` (worktree `Metis-novelty-queries`)
- Base: `4eb8c56` (`main`; merge-base equals current `main`)
- Commits reviewed: `aa3e471` (fix), `4eaee24` (docs/fidelity), `3d83d54` (plan criteria)
- Scope: `git diff 4eb8c56..codex/novelty-retrieval-queries`, plus reading `references.py`,
  `behavior.py`, `evaluation.py` and `research_stages/seeds.py` for context. No source was
  modified. No network or model calls were made.

## Checks run

| Check | Result |
| --- | --- |
| `uv run --no-sync python -m pytest -q tests/test_literature.py tests/test_review.py tests/test_writer_literature_substitution.py tests/test_fidelity_matrix.py` | 70 passed. There are no `tests/test_references*.py` files. Citation audit (`references.py`) is covered in `tests/test_review.py`, which was run in their place. |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync mypy src` | No issues, 87 files |
| `cmp docs/fidelity.json src/autoresearch/assets/fidelity.json` | Identical |
| `git cat-file -t aa3e471` | commit (the SHA in the fidelity row is real) |
| `git merge-tree --write-tree main codex/novelty-retrieval-queries` | Clean, no conflicts |
| Scratch probe of `query_terms`/`keyword_query`/`arxiv_expression`/`retry_decision` on edge inputs | See findings. All outputs were non-empty, and no arXiv operator was injected. |

## Assessment by area

1. **Keyword extraction and provider syntax.** Stopwords, research filler, code/path tokens
   (`train.py`, `learning_rate=0.01`, `a/b`, `--lr`) and number-only tokens are dropped.
   Hyphen compounds are kept and sent to arXiv as quoted phrases (`all:"bias variance"`). Unicode
   works (`über-schnelle` → `all:"über schnelle"`). User-typed `AND`/`OR`/`ANDNOT` are
   stopwords, and `ti:foo` splits into plain terms, so user text cannot become an arXiv operator
   or field prefix. httpx URL-encodes the parameters. Every `all:` term or phrase has its own
   prefix, the OR group is parenthesised, and the cutoff clause is appended with `AND` as before.
   The result is valid arXiv API syntax. Crossref (`query.bibliographic`) and S2 (`query`) get
   plain keyword strings, still truncated to 1000 characters. Edge cases (see F4):
   - If every token is filtered, the query falls back to the leading raw words, so it is never
     empty.
   - An all-punctuation input gives `all:--- AND all:---` through the short-query path. That
     path is unchanged from the base.
2. **The ≤12-word passthrough** keeps titles of 12 words or fewer exactly as before. The word
   count splits on hyphens, so some citation titles of 12 or fewer visible words are condensed
   anyway (F2). The third novelty query is still a full AND on arXiv (F1).
3. **Gates are unchanged.** `novelty_references`, the inspectable-content check
   (`min(4, novelty_references)`) and `coverage["sufficient_for_assessment"]` are untouched.
   - Fetch counts:
     - Default config: `max(12, 3, 12) = 12`, as before.
     - Live config: rises from 2 to 12.
     - The `two-references` arm sets `results_per_provider = max_results = 2`, so it still
       fetches 2.
   - Full-text inspection stays bounded by `max_full_text_papers`.
   - Merged results stay bounded by `max_results`, and the novelty prompt evidence still passes
     through the existing bounded-evidence rendering.
   - A wider candidate pool can raise the novelty judge's union to about 36 refs in the live
     config, but that is the same size as the default config's pool, so this is acceptable.
4. **Backoff** is bounded at 3 attempts with each wait capped at 60 s. Every attempt is recorded
   in `providers[].backoff`, and the sleep can be injected through `Literature.sleep`.
   `ThrottledProvider.handles_backoff` stops Literature from retrying a second time.
   `test_writer_literature_substitution.py:479-484` catches double retries indirectly: they would
   add sleeps beyond `[2.0, 4.0]`. No test asserts the guard directly (F5). The records hold only
   status, error class, Retry-After and wait time. No headers are recorded, and the S2
   `x-api-key` never enters `detail`. The provider query is recorded, but it contains only
   hypothesis or title text, never credentials.
5. **Cache and identity.** The in-process cache key is still the raw `(query, limit, cutoff)`.
   Provider-query derivation is deterministic, so cache hits stay consistent.
   `behavior.runtime_manifest()` hashes every `.py` file under the package, so this change
   changes the runtime behavior identity. Pending runs started on the old code will be detected
   as drift and not silently resumed under the new query semantics. That is the intended
   protection, but rerunning in-flight live runs needs a fresh run. No persisted retrieval cache
   is keyed by provider query, and evidence IDs do not depend on the query.
6. **Fidelity and docs.**
   - The novelty row lists `aa3e471` and the plan as evidence, and the remaining gap says that
     the effect on live relevance is unmeasured. The wording is honest.
   - The `fidelity.json` mirror and both rendered tables are in sync.
   - `paper-orchestra.md` and the D04 row in `paper-spec.md` say that writer foci longer than
     12 words are condensed.
   - The plan claims title lookup is "sent as before". That is not exactly true (F2).
7. **Tests.**
   - They discriminate:
     - the arXiv test asserts 8 `all:` terms and 4 `AND`s, against about 30 before;
     - the S2 429 → success test asserts the sleep, the backoff record and both queries;
     - the capped-503 test asserts `[60, 60]` and no retry on 400;
     - the fetch-count test asserts `calls == [12]`.
   - Gaps: no test for an HTTP-date `Retry-After`, for the `handles_backoff` guard directly, or
     for a long title in citation audit.
8. **Merge.** `merge-tree` against `main` is clean.

## Findings

| # | Severity | Location | Finding | Recommended fix |
| --- | --- | --- | --- | --- |
| F1 | Medium | `src/autoresearch/research_stages/seeds.py:122`, `src/autoresearch/literature.py:113` | The third novelty query, `title + " alternative prior methods limitations"`, is usually 12 words or fewer, so it keeps the all-terms conjunction. For example, `Attention Is All You Need alternative prior methods limitations` → 9 ANDed terms, including `Is`, `All`, `methods` and `limitations`. On arXiv this is very likely to return 0 results, which is the same defect class this branch fixes. It does not break any gate because coverage uses the union of the queries, but it wastes arXiv's share of the query. | **Fix now.** Make the mode explicit instead of relying on a length heuristic: give `search`/`search_external`, or the providers, a `title_lookup` flag (or a `kind="title"\|"topic"` argument). `references.py` and writer task foci would pass the raw title; the novelty queries would always use the keyword path, with the arXiv core/OR form for any multi-term topic query. The smaller alternative is to build the third novelty query from `query_terms(title) + ["limitations"]` and apply the core/OR form whenever the arXiv input has more than 3 terms after filtering. |
| F2 | Medium | `src/autoresearch/literature.py:91-93`, `src/autoresearch/references.py:94` | The passthrough counts `[^\W_]+` tokens, so hyphens split words. Citation audit (`search_external(reference.title, 5)`) therefore condenses some ordinary titles. For example, `Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer` has 11 visible words, counts as 14 tokens, and is sent to arXiv as 3 required terms plus an OR group, and to S2 as lowercase keywords. It will probably still be found, but citation re-retrieval does not behave "exactly as before", contrary to the plan's claim. | Fixed by the same explicit title mode as F1, with a regression test for a long hyphenated title in `tests/test_review.py`. Failing that, correct the plan wording. |
| F3 | Low | `src/autoresearch/literature.py:680-706`, `src/autoresearch/references.py:94` | The new Literature-level retries also apply to citation audit and every other `search_external` caller, not only to novelty. With `Retry-After: 60`, one provider can now wait up to 120 s per cited reference. Previously it failed immediately. | Document this in the plan and fidelity notes as an accepted latency cost. Alternatively, let callers pass an attempts or budget override. |
| F4 | Low | `src/autoresearch/literature.py:85-88`, `141` | (a) The all-filtered fallback reintroduces the tokens the filter just dropped: `train py config yaml lr 0 1 1e`. (b) `Retry-After: inf` or `1e9` is recorded as `retry_after: inf`, and `json.dumps` writes non-standard `Infinity` into the search report. The wait itself is correctly capped. (c) A past HTTP date or `0` gives an immediate retry. | (a) Fall back to non-stopword alphabetic tokens before raw words. (b) Record `min(retry_after, MAX_BACKOFF_SECONDS)` or `None` for non-finite values. (c) Optionally use a small floor such as 1 s. |
| F5 | Low | `tests/` | No direct test that a `handles_backoff` provider is attempted once per Literature call, and no test for an HTTP-date `Retry-After`. The guard is covered only indirectly by the writer sleep sequence. | Add a fake provider with `handles_backoff = True` that raises 429, and assert exactly 1 call and no `backoff` entries. Add an HTTP-date case to `retry_decision`. |
| F6 | Info | plan "Open items" | The open risks are listed honestly: ordering-based salience, unmeasured live relevance, and keyless S2 still possibly returning 429. Behaviour on a live rerun is unmeasured. Passing tests are not evidence of retrieval quality. | Keep the plan's next step: a live novelty rerun with the provenance kept. |

## Verdict

**Approve with changes.** The core fix is sound, bounded and well recorded. Query construction
cannot inject operators, the gates and evaluation arms are unchanged, backoff is bounded without
double retries, no credentials are recorded, docs and fidelity are honest, and the merge is
clean. Before merging, fix F1, and with it F2, by replacing the length heuristic with an explicit
title-lookup and topic-query distinction (or at minimum applying the core/OR arXiv form to the
third novelty query), and add the F2 regression test. F3–F5 can follow in the same branch or be
recorded as open items.

## Author resolution

All findings were addressed on the branch after this review was committed unchanged in
`cd790ed`. The fix commit is `ef29a29`. The fidelity and documentation update follows it.

| # | Resolution |
| --- | --- |
| F1 | **Fixed.** The 12-word heuristic is replaced by an explicit query kind. `Literature.search_topic`/`kind="topic"` is used by limitation extraction and every novelty query, including `title + " alternative prior methods limitations"`. Topic queries always use salient keywords and the arXiv core/OR form. Tests: `test_short_novelty_topic_query_is_bounded_on_arxiv` and `test_novelty_stage_searches_in_topic_mode`. |
| F2 | **Fixed.** Title lookups are the default (`kind="title"`): citation audit, writer task foci and hints, and review queries. They are sent to every built-in provider exactly as before. Test: `test_title_lookup_sends_hyphenated_title_unchanged_to_every_provider`, which uses the 11-word hyphenated T5 title. |
| F3 | **Documented** in `docs/literature-identity.md`. Citation audit now retries, with a worst case of 120 s extra wait per provider and 360 s per cited reference with three providers, all recorded. There is no per-caller override: the earlier immediate failure left citations unverified, and one recorded bound keeps the interface and provenance uniform. |
| F4 | **Fixed.** (a) A topic query with no salient term sends the raw text and records a limitation; it never resurrects filtered tokens. (b) Retry-After is clamped to a finite 0–60 s before it is recorded, and NaN is ignored. (c) Zero or past Retry-After values use the exponential backoff floor (2 s, 4 s). Tests: `test_retry_after_http_date_past_zero_and_non_finite_values` and `test_topic_query_without_salient_terms_records_limitation`. |
| F5 | **Fixed.** `test_wrapper_that_handles_backoff_is_called_once_without_literature_retries` checks the guard directly, and the HTTP-date case is in the Retry-After test. |
| F6 | **Kept** as an open item: a live novelty rerun is still needed to measure relevance. |

Validation: full pytest 1153 passed and 4 skipped; ruff, mypy, spec validation and the public scan pass; the fidelity matrix (17 tests) passes. The resolution is the author's. It has not been independently re-reviewed.

## Re-review (independent, 2026-10-07)

- Reviewer: Claude (Opus 5.5), the same independent reviewer as above.
- Range reviewed: `3d83d54..769a8d5` (`cd790ed` review, `ef29a29` fix, `769a8d5` docs).
- No source was modified, and no network or model calls were made.

### Checks

| Check | Result |
| --- | --- |
| `uv run --no-sync python -m pytest -q tests/test_literature.py tests/test_review.py tests/test_writer_literature_substitution.py tests/test_fidelity_matrix.py` | 76 passed |
| `uv run --no-sync ruff check .`; `uv run --no-sync mypy src` | Passed; no issues in 87 files |
| Title-mode byte identity against base: a scratch script loaded `git show 4eb8c56:src/autoresearch/literature.py` beside the branch module, captured the `_get` URL and params for each provider class, and compared them | **All identical.** Inputs: the 3 providers (Crossref, Semantic Scholar, arXiv) with cutoff `2025-01-01`. Titles: the T5 title, "Attention Is All You Need", the BERT title, a 22-word title, a unicode/code-token title, and a hypothesis-like sentence. |
| Discrimination: the branch `tests/test_literature.py` was run against `3d83d54` sources (`git archive`, then `PYTHONPATH`) | 8 failed, 20 passed. All new or changed kind/Retry-After/fallback tests fail on the old code. The `handles_backoff` test passes there because the guard already existed. It asserts exactly one call and no sleeps, so removing the guard would make it fail. |
| `docs/fidelity.json` vs `src/autoresearch/assets/fidelity.json`; `git cat-file -t ef29a29` | Identical; commit |
| `git merge-tree --write-tree main 769a8d5` (main = `4eb8c56`) | Clean |

### Verification of findings

- **F1: resolved.** `seeds.py` sends all three novelty queries and the limitation-extraction query through `search_topic`. Injected retrievers without that method keep `search`. The third query is now bounded on arXiv, and `test_short_novelty_topic_query_is_bounded_on_arxiv` asserts that `all:Is` and `all:methods` are absent. `test_novelty_stage_searches_in_topic_mode` asserts that only the topic kind reaches the provider.
- **F2: resolved.** The default kind is `title` on `search`, `search_external` and each built-in provider. The other callers are:
  - `references.py:94` (citation audit),
  - `paper_orchestra_worker.py:625` (writer foci and hints),
  - `review.py:318` (review queries),
  - `intake.py:88` (intake tool).

  None of them pass a kind, so all get title mode. Their provider request params are byte-identical to base `4eb8c56` (table above). `ThrottledProvider` forwards `kind` only when the wrapped provider declares `query_kinds`; injected providers keep the old 3-argument call and get the raw query.
- **Cache key:** adding `kind` to the in-process key only separates title and topic entries for the same text. No key is persisted, and `query_kind` is an additive report field. No harm found.
- **F3: resolved.** `docs/literature-identity.md` documents the worst-case extra wait, 120 s per provider and 360 s per reference. It also gives the reason for not adding a per-caller override. The wording is accurate.
- **F4: resolved.**
  - Retry-After clamping, verified by probe:
    - `inf` and `1e9` → 60.0;
    - `nan` → `None`, then backoff;
    - `0`, `-5` and a past date → 0.0 recorded, with a backoff floor of 2 s or 4 s.
  - A positive Retry-After below the floor is honoured as given, which matches the docs.
  - A topic query with no salient term sends the raw text and records a limitation. The raw text then goes through the old conjunction, which can include code tokens. That is acceptable because it is disclosed.
- **F5: resolved.** There is now a direct `handles_backoff` test and an HTTP-date Retry-After test.

### Remaining observations

- **Info (not blocking).** Agent-composed queries in `intake.py:88` and `review.py:318` stay in title mode, so a long free-text query there is still ANDed on arXiv. This matches base behaviour and is out of this branch's scope, but those call sites could opt into `topic` later.
- **Info.** Limitation extraction changes behaviour relative to base: it now sends keywords instead of the raw title plus objective. This is intended and documented.

### Verdict

**Approve.** F1–F5 are resolved, and title lookups are byte-identical to base. The remaining
items need no change before merge. F6 (live relevance) remains an open measurement, not a
software defect.
