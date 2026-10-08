# Quota-aware runtime routing

Base `07db7c5` (main). Branch `codex/quota-aware-routing`, worktree `Metis-quota-routing`.

## Source requirement

Live free-tier run `c37a5b021ddd` (2026-10-07/08) showed provider quota handling wasting
scarce daily requests. The coordinator asked for quota-aware routing: classify 429s,
remember exhausted models across stages and restarts, wait only when every permitted
model is unavailable, guard requests that can never fit, and keep accounting exact.

## Live evidence summary (redacted numbers only)

Read from the private run store; no private content is copied.

- Gemini free tier, `gemini-3.8-flash`: 20 requests/day/project/model. The 429 body has a
  `google.rpc.QuotaFailure` violation (quota id
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, value `20`) and `RetryInfo`
  `retryDelay` about 85101 s. Per-minute 429s carry short delays (for example 29 s).
- With `retries = 8`, one daily-quota failure made up to 9 in-request attempts although
  the reset was about 24 h away, so a single probe could use 9 of 20 daily requests.
- Quota wait then probed hourly (`provider_quota_wait` at 20:58, 22:02, 23:06 and 00:04
  UTC with `retry_after` 10919, 7076, 3233 and 86157 s).
- Other models on the same key (`gemini-3.5-flash`, `gemini-3.6-flash`) still returned
  HTTP 200: quotas are per model.
- A single 1.4M-character prompt exceeded the per-minute token quota (bounded separately
  by `evidence_context`); a request too large to ever fit looked like a transient 429.

## Boundary

- Owned files: `providers.py` (classification, `RequestTooLarge`), `routing.py`
  (`fallback_routes(unavailable=...)`, `model_limits`), `agents.py` (exhaustion
  tracking, probes, size guard), `contracts.py` (`ModelQuotaExhaustion`,
  `RunState.model_quota_exhausted`), `quota_wait.py` (`reset_delay`,
  `prune_exhaustion`), `engine.py` (persist, probe flag, wait delay), `memory.py` and
  `paper_orchestra.py` (exclude the new field from prompts/fingerprints), docs, tests.
- Not touched: `model_inventory.py` and settings UI (owned by `codex/provider-presets`).
  Per-model limits are read defensively; the interface is in
  [model routing](../model-routing.md#optional-request-size-guard).
- No change to scientific stages, prompts, workflow edges, budgets or the opt-in default
  of quota waiting. Protected routes are never swapped.

## Design

1. `providers.quota_window` classifies a 429 as `short` (advertised delay at most
   `SHORT_WINDOW_SECONDS` = 60 s) or `long` (longer delay, a daily-or-longer
   `QuotaFailure` quota id, or `x-ratelimit-remaining-*: 0` with a reset beyond 60 s).
   `long` raises immediately after one attempt with `rate_limited`,
   `quota_exhausted_until` (absolute UTC ISO) and `quota` metadata. Unknown reset for a
   daily quota: `UNKNOWN_RESET_SECONDS` = 3600. Short windows keep bounded retries.
2. `AgentRunner` records exhaustion into `RunState.model_quota_exhausted` (key
   `base_url|model|api_key_env`) and a `model_quota_exhausted` event. The engine merges
   runner records and prunes expired ones before every save. Fallback excludes exhausted
   pool models from the two alternative slots (next model in existing cost order) and
   skips an exhausted primary without a request (`model_quota_skipped` when no
   alternative remains). The field is excluded from `research_view` and the writer
   fingerprint, so prompts and cache keys are unchanged.
3. Errors carry the earliest reset among exhausted permitted models. The engine uses
   `reset_delay` (earliest reset, at least 1 s, at most `max_interval_seconds`) when it
   is known, else the existing backoff. A capped wake-up sends no request. After a wait,
   `AgentRunner.single_attempt` makes the first calls one attempt (reservation and
   transport); the cache key keeps the configured route.
4. `_guard_size` uses optional `context_window_tokens` / `tokens_per_minute` metadata
   and `ceil(request_input_bound / 4)`. Oversized: event, no reservation,
   `RequestTooLarge`; fallback tries the next model; none fits: blocking non-rate-limited
   error.
5. Protected routes: exhausted model → no request, non-recoverable rate-limited error →
   quota wait if enabled, else blocked.

## Acceptance

- Daily 429 → one attempt; `quota_exhausted_until` from RetryInfo; QuotaFailure
  metadata parsed; per-minute 429 → bounded retries; OpenAI reset headers.
- Fallback skips an exhausted model across steps and a new engine (restart); exhausted
  models free their alternative slot; reset → eligible again.
- All exhausted → wait until earliest reset; capped wake-up sends no request; disabled
  → blocked.
- Protected route exhausted → not swapped, non-recoverable, reset delay.
- Oversized → skip with event; none fits → blocked, no call; no metadata → inactive.
- Accounting: one charge per attempt; probe reservation one attempt; skipped calls free.
- Existing quota-wait/fallback suites pass (their 429 fixture now uses a 45 s
  short-window `Retry-After`; 90 s is long-window under the new rule).

## Known limitations and open risks

- Classification thresholds (60 s, daily markers, 1 h unknown reset) are hypotheses
  from one provider's free tier; live recovery after a real Gemini reset is untested.
- `research_view` still includes `quota_wait_*` counters, so a probe prompt differs by a
  few bytes from a normal one (pre-existing; changing it would alter every cache key).
- The size guard depends on metadata the inventory schema does not yet define; the
  bytes/4 estimate can mis-estimate non-English or highly compressed text.
- Existing runs pick up the runtime behavior on resume (no configuration change); the
  new RunState field defaults to empty.
- A quota-wait wake-up still re-enters the stage handler; non-model work before the
  first model call (for example literature retrieval) may repeat, as before.

## Validation history

- The new suite first failed on test fixtures only: equal model prices let inventory
  routing pick `backup` first, and a handler re-entered the same stage (undeclared
  edge). Fixed in the tests by distinct prices and alternating declared edges.
- Existing `test_provider_quota_wait.py` fallback fixture used `Retry-After: 90`, which
  is now long-window; changed to 45 s to keep testing the short-window path.
- The first full run (`-x`) failed in `tests/test_writer_supervision.py`: the test
  recomputes the writer fingerprint and needed the same `model_quota_exhausted`
  exclusion. The exclusion keeps fingerprints of existing runs unchanged.

## Final validation (feature commit `767aaba`)

| Command | Result |
|---|---|
| `uv run --no-sync ruff format --check .` | 173 files already formatted |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync mypy src` | No issues in 87 source files |
| `uv run --no-sync metis validate-specs` | exit 0 |
| `uv run --no-sync python -m pytest -q tests/test_quota_aware_routing.py` | 19 passed |
| `uv run --no-sync python -m pytest -q` | 1182 passed, 4 skipped (369 s) |
| `node --test tests/*_ui.mjs` | 107 passed |
| `uv run --no-sync python scripts/scan_secrets.py` | passed |
| `metis demo` (scratch `AUTORESEARCH_HOME`) | exit 0; stage `complete`, status `completed` |

No check makes a real provider request. The fidelity matrix is unchanged: this is
runtime routing, not a scientific stage. Independent review is pending.
