# Writer literature discovery substitution (D04)

Status: implemented and tested on `codex/writer-literature-substitution` from `main` (`bc15d64`).
Feature commit `aaf1265`. Independent review is still required before merge; none is claimed here.

## Requirement and observed defect

Live evidence (2026-10-07): the official PaperOrchestra literature stage discovers candidate papers
with native Gemini plus the `google_search` tool, then verifies titles with Semantic Scholar. On a
Gemini API free-tier key, grounded `generateContent` returns 429 quota immediately on current flash
models and `gemini-2.5-flash` returns 404 for new users; ordinary ungrounded calls work. The writer
therefore cannot run without paid grounding.

`docs/paper-spec.md` deviation D04 already permits literature search through another provider or
curated corpus, provided query, retrieved sources, timestamp and coverage limitations are recorded,
and an offline empty search never certifies novelty.

## Primary-source inspection

Pinned upstream `ca1b3fa01c2970fc7cda32d16245db38d57b3f56`,
`methods/agents/literature_review_agent.py`:

- `HybridLiteratureAgent.run` → `_collect_search_tasks(outline)` builds search tasks from the
  official outline (`search_directions`, `limitation_search_queries`, `citation_hints`). No model or
  search call is involved in query generation.
- `_execute_tasks_in_parallel` calls `_process_search_task_google` → `_discover_candidates(task,
  outline, cutoff)`. Only `_discover_candidates` uses Google Search (hard-coded model
  `gemini-3-flash-preview`, independent of `literature_model_name`). It returns
  `CandidatePaper(title, year, reason)` items; exceptions and empty results are swallowed and
  retried up to three times.
- Each candidate then goes through `_enrich_and_register_paper` → `s2_title_search` (Semantic
  Scholar title matching, cutoff and abstract filtering), BibTeX/citation-map generation, outline
  citation injection, and `_synthesize_content` (ungrounded, uses `literature_model_name`).

## Chosen seam and boundary

Narrowest seam: override only `_discover_candidates` in a Metis-side subclass of the pinned
`HybridLiteratureAgent`, created inside the worker. The query for each task is the official task
`focus` produced by the official `_collect_search_tasks`, so the official agent's own query
generation is reused without Google Search. Candidates come from Metis `Literature.search_external`
(Semantic Scholar / arXiv / Crossref per `LiteratureConfig`). Everything downstream (S2 title
matching via the instrumented `requests.get`, cutoff filter, BibTeX keys, citation map, outline
injection, section writing, reflection, Evidence export) stays official and unchanged. The pinned
checkout is not modified.

Configuration: `paper_orchestra.literature_discovery: "google_grounded" | "metis_retrieval"`,
default `google_grounded` (unchanged behavior). Empty `literature_model_name` reuses the resolved
writer model (upstream's literature synthesis is an ordinary ungrounded writing call), avoiding a new
catalog upstream slot. Full-text inspection is disabled for discovery because only titles are used.

## Acceptance criteria

1. Default mode unchanged; preflight still requires `GEMINI_API_KEY` for grounding.
2. `metis_retrieval` routes discovery through Metis retrieval; official downstream receives the
   candidates; no Google Search tool call is made.
3. Provenance per query (backend, deviation, task, exact query, cutoff, timestamp, providers,
   raw responses, identifiers, failures, limitations) in `literature-discovery.jsonl`, plus a
   summary `literature-discovery.json` marking the D04 substitution and `novelty_certified: false`.
   Exported `Evidence.retrieval` records the discovery backend.
4. All providers failing for a query records a failed request receipt, so the literature
   checkpoint cannot complete. A stage with zero discovered candidates fails explicitly.
5. Preflight with `metis_retrieval`, `use_plotting=false` and compatible text models does not
   require `GEMINI_API_KEY`.
6. Job fingerprint changes with the option; default-mode fingerprints of existing jobs are
   preserved by omitting the default value from resolved options.

## Validation record (2026-10-07, macOS, Python from `uv sync --frozen --group dev --extra evaluation`)

No network, paid model or Docker/TeX calls. All retrieval, S2 and model responses are fakes.

- `uv run --no-sync ruff format --check .` / `ruff format .`: 170 files unchanged.
- `uv run --no-sync ruff check .`: all checks passed.
- `uv run --no-sync mypy src`: no issues in 86 source files.
- `uv run --no-sync metis validate-specs`: passed (workflow digest printed).
- `uv run --no-sync pytest -q tests/test_writer_literature_substitution.py`: 9 passed.
- `uv run --no-sync pytest -q -x -p no:cacheprovider` (code commit): 1102 passed, 4 skipped.
- `uv run --no-sync pytest -q -p no:cacheprovider` after the docs/fidelity update: 1102 passed, 4 skipped.
- `uv run --no-sync pytest -q tests/test_fidelity_matrix.py tests/test_package.py`: 17 passed, 1 skipped.
- `node --test tests/*_ui.mjs`: 106 passed.
- `uv run --no-sync python scripts/scan_secrets.py`: public-file scan passed.
- `uv run --no-sync metis demo`: completed (synthetic; outcome
  `previous_best_retained_meta_refinement_not_superior`).
- Official-writer job equivalent: a separate environment (`uv sync --frozen --group dev` into a
  scratch venv, then `uv pip install --require-hashes -r .docker/paper-orchestra-requirements.txt`)
  with the pinned checkout at `ca1b3fa…` (`verify_checkout` passes):
  `PAPER_ORCHESTRA_TEST_CHECKOUT=<checkout> AUTORESEARCH_UPSTREAM_FIXTURE=<checkout> PYTHONPATH=src
  python -m pytest -q tests/test_writing_upstream.py tests/test_writer_recovery.py`: 11 passed.
  The new upstream test runs the real `HybridLiteratureAgent.run` with the D04 subclass: the official
  S2 title match, BibTeX key `Lovelace2024SparseAttention`, citation map and synthesis call all
  received the Metis-retrieved candidate; a `google_search` tool call was refused.
- In the same environment, `autoresearch.paper_orchestra_worker._metis_literature` imports and builds
  the retriever using only packages pinned in `.docker/paper-orchestra-requirements.txt`
  (`click`, `httpx`, `idna`, `pygments`, `rich` are the extra third-party imports; all pinned).

## Open risks

- No live run: the substitution is unvalidated against real Semantic Scholar/arXiv/Crossref rate
  limits inside the Docker worker, and its citation quality versus Google grounding is unmeasured.
- Queries use only the task focus; the grounded prompt also supplied task context and the project
  problem. Targeted hints take the first merged retrieval result, which can be the wrong paper;
  official S2 fuzzy title matching then verifies only that title, not that it is the intended work.
- Default-mode job identity is preserved by omitting the default option value; the new
  `literature_model_name` inheritance applies only to an explicitly empty value.
