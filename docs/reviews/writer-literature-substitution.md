# Review: writer literature discovery substitution (D04)

- Reviewer: independent review agent (Claude), 2026-10-07
- Branch: `codex/writer-literature-substitution` (worktree `Metis-writer-lit`)
- Base: `bc15d64`
- Commits reviewed: `aaf1265` (feat: opt-in D04 Metis retrieval for writer literature discovery),
  `2615491` (docs: document D04 writer literature discovery substitution)
- Pinned upstream inspected: `~/.local/share/metis-upstreams/paper-orchestra` at
  `ca1b3fa01c2970fc7cda32d16245db38d57b3f56`
- No network, paid model, Docker or TeX calls were made.

## Checks

### 1. Seam against pinned upstream: pass

- In `methods/agents/literature_review_agent.py` the only Google Search use is
  `self.google_search_tool` (line 87, constructed but inert) passed in `_discover_candidates`
  (lines 426-475, hard-coded `gemini-3-flash-preview`). A repository-wide search of the pinned
  checkout finds no other `google_search`/`GoogleSearch` use, so overriding only
  `_discover_candidates` removes all grounded search.
- `discovery_agent` defines a subclass overriding only `_discover_candidates`; `run`,
  `_collect_search_tasks`, `_process_search_task_google` (3-try retry, exception swallowing),
  `_enrich_and_register_paper`, `_is_paper_allowed`, `_synthesize_content`, key/BibTeX/citation-map
  generation and the writer prompts are inherited unchanged. The pinned checkout is not modified
  (`verify_checkout` still governs it).
- Shape: upstream returns `parsed_response["candidates"]` as plain dicts and
  `_enrich_and_register_paper` reads them with `getattr(...) or cand.get(...)`. The substitute
  returns `{"title", "year", "reason"}` dicts, matching. `year` may be `None` when a provider has no
  date; upstream passes it as `year_hint` to `s2_title_search` (accepts `None`) and falls back to
  the S2 year, so this is safe.
- The Transports refusal of `google_search` tools is effective because upstream builds
  `types.GenerateContentConfig(**generation_configs)` (`utils/gemini_utils.py:159`), which the
  worker `model_dump`s to dicts before the check.

### 2. Scientific fidelity of queries: acceptable as a documented D04 substitution

- Exploration queries use the official task `focus`, which upstream generates as search strings
  (`search_directions`, `limitation_search_queries`, or the subsection title/cluster fallback).
  Upstream's `context` is long hypothesis prose (`Hook: ... Gap: ...`, `Mission: ...`) and the
  project problem; appending it to Semantic Scholar/arXiv/Crossref keyword queries would likely
  degrade recall rather than restore the grounded model's reasoning. Using `focus` only is the
  defensible choice for keyword retrieval.
- Targeted hints taking the first merged result (default provider order: Semantic Scholar, arXiv,
  Crossref) is the weakest part: a hint such as "paper introducing dataset X" can yield a wrong
  must-have citation, and official S2 matching then only verifies that the wrong title exists.
  This is honestly disclosed in `literature-discovery.json` `coverage_limitations`, in
  `docs/paper-orchestra.md` and in the plan, provenance links every citation to its proposing query,
  and a separate citation-support integrity check exists. Not merge-blocking (finding F2).

### 3. Default-mode safety: pass

- Verified directly: `resolve_writer_config(ResearchConfig())` serialized with `sort_keys` hashes
  identically on base `bc15d64` and the branch
  (`65fcd863ca3d98f3f187bca2fc85c43a9b4dcd17700a3828a5c882febe0115f8`), so the run fingerprint
  (`[state, options, catalog.digest]`) and default-mode resumability are unchanged.
- Preflight default branch is unchanged (`GEMINI_API_KEY` grounding error retained). Its report gains
  an additive `literature_discovery` key, and `unpriced_native_models` now skips compatible
  aliases; neither affects default configurations.
- The empty-`literature_model_name` inheritance (`paper_orchestra.py:221`) applies in both
  discovery modes, so it does alter `google_grounded` behaviour, but only for an explicitly empty
  value, which previously sent `model_name=""` to native Gemini and could not work. The default
  `gemini-3.1-pro-preview` is unaffected. Informational (F4).

### 4. Worker isolation and credentials: pass

- The Docker command is unchanged apart from passing
  `literature.semantic_scholar_api_key_env` (via the existing `resolve`) only when
  `metis_retrieval` is set; tested for both modes. The name is also added to the worker's redaction
  set. The container's network is the existing default egress (already used for S2/Gemini); arXiv
  and Crossref hosts are newly contacted, but no new mounts or capabilities are added.
- Provenance contains no credentials: the S2 key is sent only as an `x-api-key` header, which is
  never recorded; recorded `endpoint`/`parameters` are query, limit, fields and date filters; the
  Crossref endpoint is fixed to `https://api.crossref.org/works`; exceptions are reduced to
  type names/HTTP status. Job options store only the env var name.
- Google Search tool calls are refused in this mode before any compatible/native dispatch, covered
  by both the unit test and the real-upstream test using real `types.Tool(google_search=...)`.

### 5. Failure handling and accounting: pass

- Each discovery runs inside `CallJournal.observe` with stage-scoped receipts (stage propagated
  through upstream's pools by `propagated_stage_context`). An all-provider failure raises inside
  `observe`, writes a failed receipt, is swallowed and retried by upstream, and stays unresolved
  unless an identical request later completes, so `StageJournal.run` refuses the literature
  checkpoint (tested). Failed attempts are never cached; each retry builds a fresh retriever.
- Successful retrievals (including completed-but-empty ones) are cached in `discovery_cache` and
  replayed with a `replayed` row; empty totals fail explicitly in `finish()` after writing the
  summary with `novelty_certified: false`. If retrieval finds candidates but official S2 rejects
  all of them, the existing `export_evidence` "no evidence" failure still fails closed.
- Partial provider failure records `status: completed` with per-provider failures and limitations
  in both log and summary; this is recorded, not silent.

### 6. Fidelity docs and matrix: pass

- `draft` and `revise` rows updated identically in `docs/fidelity.json` and
  `src/autoresearch/assets/fidelity.json` (byte-identical), `docs/fidelity.md` and
  `fidelity-report.md`. `aaf1265` exists. Status stays `integrated` (default path still runs
  released code) and `remaining_gap` explicitly states no measured parity with Google-grounded
  discovery. D04 in `docs/paper-spec.md` and `docs/paper-orchestra.md` are consistent with the code.

### 7. Tests and static checks: pass

- `uv run --no-sync python -m pytest -q -p no:cacheprovider tests/test_writer_literature_substitution.py tests/test_fidelity.py tests/test_fidelity_matrix.py tests/test_writer_accounting.py tests/test_writer_recovery.py tests/test_writer_supervision.py tests/test_writing.py tests/test_writing_upstream.py tests/test_writer_prompts.py`:
  98 passed, 3 skipped (upstream-checkout tests skip without the special venv).
- `uv run --no-sync ruff check .`: all checks passed. `uv run --no-sync mypy src`: no issues in 86
  files.
- The new tests cover default identity, preflight in both modes, credential passing, routing of
  official queries, replay, empty failure, provider outage blocking the checkpoint, evidence
  provenance and `_execute` wiring. The new `test_writing_upstream` test (not run here; needs the
  pinned runtime) is sound: it drives the real `HybridLiteratureAgent.run` through the subclass and
  asserts the official S2 title query, BibTeX key, citation map and synthesis receive the Metis
  candidate. Its S2 stub echoes the query title, so it proves wiring, not matching quality.

### 8. Merge compatibility with `main` (`c13f1c4`): pass

`git merge-tree --write-tree main codex/writer-literature-substitution` returns a tree with no
conflicts. `main` since `bc15d64` (provider quota wait) touches none of the branch's files;
`_metis_literature` validates a `ResearchConfig` from only literature/search fields, which remains
valid with main's new config defaults. Re-run the full suite after merging.

## Findings

| ID | Severity | Location | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| F1 | Low | `src/autoresearch/paper_orchestra_worker.py:434`, `:479` | Retrieval cutoff is the inclusive month end of `research_cutoff`, while official `s2_title_search` admits only papers before the first of that month. Candidates from the cutoff month are proposed and then dropped downstream, and the recorded `cutoff` overstates the effective one. | Use the day before `YYYY-MM-01` (matching upstream S2), or record both the retrieval and the official effective cutoff. |
| F2 | Low-Medium (scientific, non-blocking) | `src/autoresearch/paper_orchestra_worker.py:498` | Targeted hints retrieve exactly one merged result, so a wrong must-have paper is plausible and no alternatives are retained for audit. | Follow-up: retrieve a small top-k (e.g. 3-5) for targeted tasks, retain all in the log, still return one candidate; consider preferring a candidate whose title shares salient hint tokens. Keep the disclosed limitation. |
| F3 | Low (live-run risk) | `src/autoresearch/paper_orchestra_worker.py:544` | Upstream's 3 immediate retries times many tasks against keyless S2/arXiv with no throttling may hit rate limits. Persistent per-provider failure is recorded but does not block while another provider completes. | Before a live run, add bounded backoff between discovery requests or document the expected degraded coverage; inspect `provider_failures` in the summary. |
| F4 | Info | `src/autoresearch/paper_orchestra.py:221` | Empty `literature_model_name` inheritance also applies in `google_grounded` mode (previously an unusable configuration). Default value unaffected. | Optional: mention in `docs/paper-orchestra.md` that the inheritance is mode-independent. |
| F5 | Info | `src/autoresearch/paper_orchestra_worker.py:493` | An empty task focus (e.g. a blank `citation_hints` entry) raises `ValueError` in retrieval and blocks the whole literature stage, whereas grounded discovery would tolerate it. | Optional: record such a task as skipped with a limitation instead of a failed receipt. |

## Verdict

Approve for merge. No blocking findings. The seam is the narrowest correct one against pinned
`ca1b3fa`, default mode is byte-identical in resolved options, provenance and fail-closed behaviour
meet D04, and the classification honestly states no measured parity. F1-F3 are recommended
follow-ups before any live or comparative use of `metis_retrieval`.
