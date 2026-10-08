# Automatic price/performance model selection per agent role

Base `808a74b` (main: provider presets + quota-aware routing). Branch
`codex/model-selection`, worktree `Metis-model-selection`.

## Source requirement (2026-10-08)

The user has no budget and enters keys for several providers (Gemini free tier with
20 requests/day per model, Mistral free mode, Groq free 1K RPD but 8K TPM, Cerebras
free 1M tokens/day and 30K TPM, OpenRouter free 50 RPD, local Ollama; paid plans
possible). Metis should "optimize for price and performance, with automatic (smart,
probably agent based) selection" of models for each agent role.

Before this change, inventory routing gave every routine role the single cheapest
model by list price and every other role the configured primary (or the first usable
inventory entry). Free-tier quotas, context windows, tokens-per-minute limits,
JSON-mode support and published capability tiers were stored but not used to choose.

## Design (hybrid)

1. **Deterministic planner** (`model_selection.plan_models`, no model calls). Runs
   inside `prepare_models`, so at creation, `metis check` and the setup preview.
   For every routable role it estimates expected calls (policy formula over the
   pipeline/coding configuration) and prompt size (policy estimate per handler,
   replaced by the recorded p90 when at least five outcomes exist). It filters the
   frozen permitted pool by hard constraints: context window ≥ prompt × margin +
   output, tokens/minute ≥ prompt + output, JSON mode, a capability floor for
   critical roles (provider-published tier ≥ `standard`; unknown tiers stay eligible
   and rank like `standard`), "not available on the free tier", and an
   optional exclusion of free tiers with a data-use caveat. Ranking: critical roles
   by capability, then free before paid, then configured primary, then cost; routine
   roles by expected charge, then observed failure rate, then capability. Within the
   best band, roles go to the model with the lowest projected quota load, which
   spreads routine work across free models. It reports per-model calls/tokens,
   days-to-complete when published daily quotas bind, list-price equivalent cost and
   expected charge.
2. **Agent refinement** (`model_router`, opt-in: `model_selection.router` = `auto`
   (default: on only with ≥ 2 eligible models) / `on` / `off`). One call at the first
   Start/Step/Resume of the run, never at creation. It is a catalog agent with an
   `operational` context policy (no research state, project or evidence in the
   request), routed by the planner like a routine role, accounted, budgeted and cached
   like other calls. It may only choose among the planner's eligible candidates and
   must give a rationale per role. Deterministic validation rejects unknown roles or
   models, candidates outside the eligible list, duplicates, missing rationales,
   missing roles and expected charges over the run budget. Any failure keeps the
   planner plan and records why. The run never blocks on it.
3. **Freezing.** Planner routes are written into the run configuration
   (`role_providers` + `planned_routes`) and therefore into the behavior bundle. The
   refinement is sealed in `RunState.model_plan` with an immutable, hash-verified
   artifact applied as an ephemeral execution view each step (same pattern as the
   sealed research protocol). `fallback_routes` uses the frozen per-role order;
   exhausted models are skipped and the next planned model takes the slot.
   Artifacts: `model-plan.json` at creation (`model_plan_created` event),
   `model-plan-refined.json` at Start (`model_plan_refined` /
   `model_plan_router_rejected` / `model_plan_router_failed` events).
4. **Observed outcomes.** A private cross-run `model_outcomes` table in the Store
   records per (role, model) attempt outcomes already observable: schema-valid on the
   first attempt, repaired, schema-invalid, provider failure, latency, cost, tokens.
   The planner uses them only as an "observed" signal with sample counts shown; they
   are never presented as research-quality parity.
5. **Surfaces.** `metis check` / setup readiness gains a `model-plan` check and a
   `model_plan` summary; the run's AI system view (CLI/TUI text and browser) shows the
   final per-role routes with reasons, estimated cost and quota days.

## Boundaries

- Owned: `model_selection.py` (new), `model_inventory.py` (`prepare_models` calls the
  planner), `routing.py` (`fallback_routes(role=...)`), `agents.py` (operational
  context, plan-ordered fallback, outcome recording), `engine.py` (creation artifact,
  router at Start, ephemeral plan view), `contracts.py` (`RunState.model_plan`),
  `config.py` (`ModelSelectionConfig`, `planned_routes`), `store.py` (outcome table),
  `catalog.py` (`operational` context policy, selection policy schema), `specs/`
  (`model_router` agent and prompt, `policies/models.json` selection policy, catalog
  version bump), `memory.py`/`paper_orchestra.py` (exclude `model_plan` from
  model-facing views and fingerprints), `setup.py`, `behavior.py`, `system_view.py`,
  `static/app.js`, docs, tests.
- Unchanged: scientific stages, gates, workflow edges; held-out evaluator, explicit
  panels, frontier escalation, external commands, native writer slots and explicit
  role overrides keep their fixed routes; no stage is removed for cost. No rule in
  the paper specification requires critics to use a different model from producers
  (D07: preserve separate invocations even on the same endpoint); the planner keeps
  separate invocations and does not claim model diversity.

## Acceptance criteria / tests

- Planner: context/TPM/JSON/critical-tier constraints; quota spreading and days
  estimate; free vs paid ranking; critical roles never on a light-tier model;
  protected roles untouched; no model call at creation (`tests/test_model_selection.py`).
- Router: valid output applied and frozen; invalid choice → planner retained and
  recorded; provider failure → planner retained; disabled/auto with one model → no
  call; refined plan used by `fallback_routes` and `resolve_route`.
- Stats recorded for valid/repaired/invalid/provider-failure attempts.
- Existing suites unchanged in behavior (inventory, fallback, quota-aware routing).
- Full CONTRIBUTING checklist; independent review in `docs/reviews/model-selection.md`.

## Implementation notes

- Planner policy data lives in `policies/models.json` → `selection` (version 1);
  `catalog.py` validates it (unknown roles, non-positive estimates fail closed).
- `model_selection.plan_models` is called from `model_inventory.plan_and_prepare`
  (`prepare_models` keeps its signature). A frozen run configuration
  (`planned_routes` already set) is never re-planned, so readiness checks on an existing
  run do not show a misleading empty plan.
- Paid models are never balanced by call count; free ones are. A band's free quota is
  filled to the run's current planned days (at least one); critical work then spills
  only to an equally capable band, routine work to the next cheapest band. This mirrors
  runtime fallback, so the expected charge includes spill to paid plans.
- The router's own panel output decides acceptance: panel aggregation would turn a low
  self-reported confidence into `refine`, which has no meaning for a validated choice.
- `operational` context policy: `AgentRunner` sends only the explicit context and does
  not split it into research-state prefix messages.
- Tests that count provider requests with ≥ 2 fixture models
  (`test_quota_aware_routing.py`, `test_provider_quota_wait.py`) now set
  `model_selection.router = "off"`; the router is tested in `test_model_selection.py`.
  `test_writer_supervision.py` mirrors the writer fingerprint exclusion list and gains
  `model_plan` (old states have no such field, so their fingerprints are unchanged).
- `metis settings set model_selection.<field>` creates the optional section
  (`settings.OPTIONAL_SECTIONS`). It is not part of the scoped model settings
  (`MODEL_KEYS`), so SSH parent snapshots are unaffected.

## Interface evidence (synthetic)

- Browser, run → Inspect → AI system → Model plan, synthetic local fixture run with a
  validated router refinement: desktop dark theme and 375 px light theme inspected; no
  horizontal overflow (`scrollWidth` 375); summary, totals and per-role rows readable;
  routes labelled with their source ("Model router, checked against the planner's
  limits"). Setup readiness shows a `model-plan` check for new configurations only.
- TUI AI system tab rendered headless (Textual `run_test`, cream theme) at 80×24 and
  120×40 against the same synthetic run: the `MODEL PLAN` section now sits directly
  under the behavior bundle (it was first placed after the long workflow listing, where
  it was effectively hidden; moved in the browser too). Summary and source line are
  readable at 120×40; at 80×24 the existing four-line reading area scrolls. The TUI also
  refreshes the view when a sealed refinement changes the plan (identity includes
  `model_plan`).

## Validation log

See the final section of [the review](../reviews/model-selection.md) for the command
results at the reviewed commit.
