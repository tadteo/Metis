# Review: README first impression

- Reviewer: Claude Opus 5.5 (independent review agent), 2026-10-07
- Base: `70a1840` (main)
- Commit: `9af3521` on `codex/readme-first-impression`
- Plan: [docs/plans/readme-first-impression.md](../plans/readme-first-impression.md)
- Scope: README.md lines 1-62, `docs/images/*`, section reordering. No files other than
  this review were changed.

## 1. Factual claims (README.md:1-62)

| Claim | Evidence | Result |
|---|---|---|
| Failures kept and fed back into later ideas | `specs/prompts/evolve.md` ("Use ALL prior successes, failures..."); fidelity.md `evolve` row; paper-spec.md:49, :70 | Supported |
| Candidate promoted only by a protected evaluator agents cannot edit | reproducibility.md:44; architecture.md:164-167 (restore from private snapshot before each experiment, Docker read-only mount); claim-integrity.md:17 | Supported for the default live executor. reproducibility.md:44 notes a custom injected backend may supply an alternative trusted boundary; local/Slurm protect by snapshot restore, not read-only mount. Acceptable for a summary. |
| Manuscript claims checked against recorded results | claim-integrity.md (numerical and statistical claim ledger, receipts) | Supported, but the enforced check is numerical/statistical; other claims go to coverage/entailment audits (claim-integrity.md:3). See F3. |
| Budgets enforced before each model call | `store.py:319-331` reserve checks USD and call count; `engine.py:343` wall-clock per engine step; `engine.py:514`, `:856` experiment count per experiment | Partially accurate. See F1. |
| Creating or configuring a run never spends | usage.md:89, :159; README "Install and configure" | Supported |
| Versioned specs, archived per run, drift on resume | ai-system.md:31; `behavior.py`; previous README text | Supported |
| OpenAI-compatible APIs and local servers | `providers.py:63`; reproducibility.md:56-58 (loopback `base_url`) | Supported; "Any" is stronger than fidelity.md `model_routing` row ("Alternative models ... require paired capability evaluation"). See F2. |
| Docker, local, Slurm execution | architecture.md:111; reproducibility.md:66 | Supported |
| Managed SSH controllers | remote.md:1-6 | Supported |
| Single maintainer | `git log` has a single author (292 commits); SECURITY.md:3 "independent research implementation" | Supported by history; not stated elsewhere in docs (fine). |
| Paid end-to-end runs not yet certified | fidelity.md:9 ("Paid end-to-end writing, Docker/TeX execution and the original 107-task research benchmark are not certified") | Supported and consistent |
| Demo caption: agents and review scores scripted; experiments run for real on synthetic data | `engine.py:125-140` (demo mode: local backend, scripted `DemoProvider`, written `benchmark.py`); usage.md:199 | Supported |

No claim contradicts docs/fidelity.md. Two phrasings are stronger than the code (F1, F2).

## 2. Quick start from a clean clone

- `metis demo` (cli.py:94, :446) forces `execution.backend="local"`, `allow_local=True`,
  no search, no role commands (engine.py:125-140). The demo benchmark imports only stdlib
  (`argparse`, `json`, `os`, `random`). Runtime deps (httpx, keyring, pydantic, textual...)
  are in `[project].dependencies`; no Docker, extras or credentials needed.
  `uv sync --frozen --group dev` is sufficient (plain `uv sync --frozen` would be too; the
  dev group only adds pytest/ruff/mypy/pre-commit, harmless).
- Default serve port is 8765: `cli.py:106` (`--port`, default 8765), `web.py:62`, `web.py:793`;
  the server prints `http://127.0.0.1:<port>` (web.py:795). README URL matches.
- `metis tui` exists (cli.py:137) and takes no required arguments.
- Plan records the demo completing in 38 s in this worktree. Not re-run here (instruction:
  no long server); code inspection agrees.
- Result: Pass.

## 3. Content preserved from the old opening

| Old content | New location | Result |
|---|---|---|
| ScientistTwo attribution with arXiv link | README.md:48-49 | Kept |
| No affiliation / no claim of reproducing performance | README.md:50-51 | Kept ("with the authors" added) |
| PaperOrchestra pinned agents; ScholarPeer Appendix G with reconstructed orchestration | README.md:51-53 | Kept verbatim |
| Fidelity report warning | README.md:57-58 | Kept, strengthened ("any output") |
| Security guide and documentation index links | README.md:59 | Kept |
| 0.1.0 experimental preview; demo synthetic; baselines do not establish quality | README.md:47, :56-57 | Kept |
| "Inspect the AI system" section | Moved to README.md:154 unchanged | Kept |
| "The paper is a cited foundation; Metis has its own identity and development direction." | Dropped | Lost (identity framing, low impact; "draws on ... extends ... with its own architecture" covers it) |
| "Multi-provider retrieval and iterative coding/inspection retain underlying evidence." | Dropped | Lost (capability sentence; partly covered by "Every model call, command, measurement ... is recorded") |

Result: Pass with one informational note (F6).

## 4. Images

- `docs/images/console-demo-dark.png`, `console-demo-light.png` (1440x900), `tui-demo.png`
  (1860x1150) exist; README relative paths (`docs/images/...`) resolve from repo root; a
  scripted check of every relative link/src/srcset in README.md found nothing missing.
- Viewed all three. They show only the demo run (`b0a73c920b50`), "Connected to
  localhost", and no host paths, usernames, keys or tokens. PNG metadata (exiftool,
  strings) contains no text chunks.
- Labelling: console header reads "OFFLINE DEMO · SCRIPTED AGENTS / SYNTHETIC DATA"; TUI
  reads "DEMO" and "Offline example · scripted agents and synthetic data"; README caption
  (line 15) repeats this. Pass.
- Alt text is meaningful. The console alt text says "the research process from
  preparation to integrity checks", but the screenshot shows Preparation as
  "NOT VISITED" (F4).
- Observation (not README scope): the console shows checkpoint time 12:41:46 while the TUI
  activity log shows 10:41:46 for the same run, i.e. the two interfaces render timestamps
  in different time zones. Side by side in the README this is visible (F7).

## 5. Voice, rendering, anchors

- Voice (VIBE.md:16-38): literal actions and costs, no omniscience or mysticism, synthetic
  examples labelled synthetic. "What sets Metis apart" is mildly promotional but each bullet
  is a concrete mechanism. "Hard budgets" is the one phrase that promises more than the
  record supports (F1). Line 3 "An open AI research platform" can be misread as
  "OpenAI research platform" (F5).
- Rendering: `<picture>` with a `prefers-color-scheme: light` `<source>` and dark `<img>`
  fallback is the GitHub-supported pattern; blank lines around HTML blocks are correct;
  `<sub>` caption and fenced `bash` block are well-formed. `width="720"` on the TUI image is
  honoured by GitHub. Note: `pyproject.toml` uses README.md as package `readme`; relative
  image paths and `<picture>` will not render in package-index metadata. No PyPI publishing
  is documented, so informational only.
- Anchors: grep for `README.md#`, `README#`, `#run-it`, `#inspect-the-ai-system` across the
  repo (docs, src, tests, workflows) found no references. Renaming "Run it" to
  "Install and configure" and moving "Inspect the AI system" breaks nothing in-repo.
  External deep links to `#run-it` (if any) would land at the top of the page. Pass.

## 6. Validation run in the worktree

- `uv run --no-sync python scripts/scan_secrets.py`: "Public-file scan passed", exit 0.
- `uv run --no-sync pytest -q tests/test_web.py tests/test_onboarding.py`: 90 passed (49 s).
- Additionally `tests/test_package.py tests/test_fidelity_matrix.py`: 17 passed, 1 skipped.
- No test asserts on the project README text; these runs confirm nothing else regressed.

## Findings

| ID | Severity | Location | Finding | Suggested fix |
|---|---|---|---|---|
| F1 | Medium | README.md:38-39 | "Spending, call count, experiment count and wall-clock limits are enforced before each model call." Only USD and call count are checked at model-call reservation (`store.py:325-331`). Wall-clock is checked per engine step (`engine.py:343`), experiment count per experiment (`engine.py:514`). accounting.md also records that an aggregate adapter's reported overrun is committed before `BudgetExceeded` stops later work, so "hard" is slightly stronger than the ledger. | "**Budget limits.** Spending and call limits are reserved before each model call; experiment and wall-clock limits are checked before each experiment and step. Creating or configuring a run never spends anything." |
| F2 | Low | README.md:42 | "Any OpenAI-compatible API" implies any compatible model works; fidelity.md `model_routing` limitations say alternative models need paired capability evaluation and local endpoints are configured via `cheap_provider` loopback `base_url` (reproducibility.md:58). | "OpenAI-compatible APIs, including local servers on loopback; ..." or add "(capability per model is not certified)". |
| F3 | Low | README.md:37 | "Manuscript claims are checked against recorded results" covers numerical and statistical claims via the ledger; other claims go through coverage/entailment audits. | "Numbers and statistics in the manuscript are checked against recorded results." |
| F4 | Low | README.md:12 | Alt text says the process runs "from preparation to integrity checks"; the screenshot shows Preparation "NOT VISITED". | "...and the research process stages through integrity checks." |
| F5 | Low | README.md:3 | "An open AI research platform" reads as "OpenAI research platform" at a glance, which conflicts with the no-affiliation stance. | "An open-source AI research platform that keeps every attempt, including the ones that failed." |
| F6 | Info | README.md:45-53 | Two sentences from the old opening were dropped (cited-foundation/identity sentence; multi-provider retrieval and coding/inspection retain evidence). Neither is a safety or attribution disclaimer. | Optional: none required. |
| F7 | Info (product, out of scope) | docs/images/console-demo-*.png vs tui-demo.png | Same run shows 12:41:46 in the console and 10:41:46 in the TUI (local vs UTC rendering). | Track separately; optionally retake screenshots after unifying, or accept. |
| F8 | Info | README.md:17-19, :67 | "Try it in a minute" excludes first-time dependency download; prerequisites line duplicated in "Install and configure". | Optional. |
| F9 | Info | README.md:2-15 | Headline is "keeps every attempt, including the ones that failed", but the demo screenshot shows "34 completed · 0 unsuccessful". The demo cannot show the differentiator it leads with. | Optional: a later demo/screenshot that includes a recorded failed attempt or rejected idea. |

## Verdict

Approve with minor changes. Quick start, attribution, disclaimers, images, rendering,
anchors, secret scan and tests all pass. Fix F1 (inaccurate budget enforcement wording)
before merge; F2-F5 are low-cost wording corrections recommended in the same change.

## Resolution (author)

- F1: replaced "Hard budgets … enforced before each model call" with the accurate per-limit
  wording (reservation for spending/calls; experiment and step checks for the others).
- F2: "OpenAI-compatible APIs, including local servers".
- F3: "Numbers and statistics in the manuscript are checked against recorded results."
- F4: alt text now says the process ends in integrity checks.
- F5: "open-source".
- F8: removed the duplicated prerequisites line; the one-minute claim is kept (the first
  dependency download is a one-time cost).
- F6, F9: not adopted; no disclaimer was lost, and a failure-showing demo is a separate change.
- F7: console/TUI timezone mismatch tracked as a separate task.
