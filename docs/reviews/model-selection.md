# Review: automatic per-role model selection

- Reviewer: independent read-only review agent (Claude Opus 5.5), spawned by the
  implementing agent with the coordinator's specification; it made no edits.
- Branch: `codex/model-selection` (worktree `Metis-model-selection`)
- Base: `808a74b` (main)
- Commits reviewed: `171a744` (feat), `9533cb4` (docs); resolution in `ed2f868` (fix),
  re-checked by the same reviewer; re-review follow-ups in `29dec35`.
- Scope: `git diff 808a74b..9533cb4`, the plan `docs/plans/model-selection.md`,
  `docs/model-routing.md`, `docs/usage.md`, `docs/ai-system.md`, `docs/accounting.md`,
  `docs/paper-spec.md` (D07), CONTRIBUTING and VIBE. No network or model calls.

## Checks run by the reviewer

| Command | Result |
|---|---|
| `pytest tests/test_model_selection.py tests/test_model_inventory.py tests/test_quota_aware_routing.py tests/test_provider_fallback.py` | 79 passed |
| `pytest tests/test_writer_supervision.py tests/test_provider_quota_wait.py tests/test_agent_specs.py tests/test_settings.py -x` | 69 passed |
| `ruff check .` / `mypy src` / `metis validate-specs` | clean / no issues in 89 files / valid |
| `node --test tests/*_ui.mjs` | 108/108 passed |
| Three offline probe scripts (fixture key stub only) | reproduced MAJOR-1 and MAJOR-2, inspected the router request |

## Findings and resolution

| # | Severity | Finding | Resolution (`ed2f868`) |
|---|---|---|---|
| 1 | major | A critical role fell back to a light-tier configured primary when every model was also excluded for size (light primary + Groq 8K TPM). | Size estimates are relaxed first while the floor and other constraints stay; the floor error is raised when the primary is below it. Test `test_critical_roles_keep_the_floor_when_no_model_fits_the_size`. |
| 2 | major | Planner ignored `budget.usd`; an over-budget plan showed "ok" and the router (paid call) was always rejected, even when repeating the planner. | Spill to charged bands only while the expected charge stays within budget (paid stays a fallback, days grow); over-budget plans warn (setup check `warning`); router allowed up to max(budget, planner estimate). Tests extended in `test_free_tier_is_preferred_and_paid_charges_are_estimated`, new `test_planner_warns_when_charge_exceeds_budget`. |
| 3 | minor | Router request contained model identities (endpoint, key variable name). | Identity stripped from the router view; outcome summaries filtered to the pool/planned roles and keyed by inventory ID. |
| 4 | minor | Coding/inspection outcomes recorded under `coding_step`/`inspection_step`, so planned roles never accumulated stats. | Recorded under the calling (planned) role. |
| 5 | minor | 429/quota errors counted as provider failures. | New `rate_limited` outcome, shown but excluded from the failure rate; test extended. |
| 6 | minor | "Never blocks" overstated; failure reason not redacted. | Reason redacted with `privacy.redact_patterns`; docs state that budget exhaustion and pause stop the step and the router is retried on the next Start. |
| 7 | minor | `model_router` planned even when it never runs. | Planned only when the router step will run (`on`, or `auto` with ≥ 2 models). |
| 8 | minor | Router had no capability floor. | `selection.capable_routine_roles = ["model_router"]` keeps the floor. |
| 9 | minor | Setup preview has no outcome stats; frozen plan can differ. | Documented in `docs/model-routing.md`. |
| 10 | minor | `model_selection` not in scoped `MODEL_KEYS`. | Intentional (SSH parent snapshots require all keys). Re-review found the documentation insufficient; `29dec35` states it in `docs/usage.md` and `docs/model-routing.md`. |
| 11 | minor | Router could worsen quota days. | Rejected when refined days exceed the planner's. |
| 12 | nit | Plan doc said unknown tiers rank below known-capable ones. | Aligned: rank like `standard`. |
| 13 | nit | Refinement not bound to the planner record. | `apply_model_plan` checks `planner_sha256`; tampered refinement test added. |
| 14 | nit | `model-plan.json` copied all store outcomes. | Filtered to the run's pool and roles; docs updated. |
| 15 | nit | "Days" label showed 1 when nothing binds. | Browser shows "Within one day" unless a model binds. |

Additional change by the author in `ed2f868`: when the configured primary is unusable,
the default route and (unless configured) frontier escalation use the model carrying
the most planned critical calls (`workhorse`), so escalations fit critical requests.

Missing tests named by the reviewer: mixed-exclusion, over-budget and tampered
refinement are now covered; an exhausted planned primary is covered at the
`fallback_routes` level (`test_unplanned_role_keeps_cost_order_fallbacks`) and by the
unchanged quota-aware routing suite; inherited-role outcome recording and a router
exception outside `ProviderError`/`ValueError` remain without dedicated tests.

## Re-review of `ed2f868`

The reviewer re-ran its probes (light primary + oversized strong model: critical roles go
to the strong model; $0.50 budget: no paid spill, router accepts the planner's routes; no
endpoint or key name in the router request) and focused tests (81 passed, ruff, mypy,
validate-specs clean). Findings 1–9, 11 and 13–15 resolved; 10 not resolved (docs);
12 not re-checked (verified by the author: the plan now says "rank like `standard`").
Two new minor issues, both fixed in `29dec35`:

- `selection.version` not bumped for `capable_routine_roles` → bumped to `"2"`.
- `workhorse` could make a 20 requests/day free model the default and frontier route,
  and frontier escalation has no fallback → models without a published daily quota are
  preferred; documented in `docs/model-routing.md`.

## Verified as correct (reviewer)

No model call at creation or setup; fixed routes (held-out, panels, commands, explicit
overrides, writer, Laya, frontier) untouched and protected; `planned_routes`/
`model_selection` omitted when unset so existing configurations hash unchanged; frozen
configurations never re-planned; behavior verification runs before the ephemeral
refinement view; `model_plan` excluded from model-facing views and writer fingerprints;
plan-ordered fallback skips exhausted models; operational context sends only explicit
context; agent 1.0.0, catalog 3.4.0, prompt outside code; fidelity matrix uses real SHAs.

## Author validation at `ed2f868` (and focused re-run at `29dec35`)

| Command | Result |
|---|---|
| `uv run --no-sync python -m pytest -q` | 1242 passed, 4 skipped |
| `ruff format` / `ruff check .` / `mypy src` | clean |
| `metis validate-specs` | valid, 49 agents |
| `node --test tests/*_ui.mjs` | 108 passed |
| `scripts/scan_secrets.py` | passed |
| `metis demo` | completed |
| `uv build --wheel` + `AUTORESEARCH_TEST_WHEEL=dist pytest tests/test_package.py` | passed (at `9533cb4`) |
| `29dec35`: full `pytest`, ruff, mypy, validate-specs, UI tests | see the plan's validation log |

Earlier full runs under heavy concurrent load twice showed
`tests/test_engine.py::test_failed_candidates_feed_all_rounds_and_do_not_create_paper`
ending `blocked`; it passes in isolation and in the unloaded full runs at `9533cb4` and
`ed2f868`, and the demo path never builds a model plan. Recorded as load-sensitive, not
caused by this change.
