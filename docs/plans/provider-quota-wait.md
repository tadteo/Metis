# Provider quota wait

Base `70a1840` (main). Branch `codex/provider-quota-wait`, worktree `Metis-quota-wait`.

## Source requirement

The user runs Metis on the Gemini API free tier (about 10 requests per minute and
daily request caps that reset daily). They asked for an option to continue when the
provider quota refreshes, instead of the run stopping on HTTP 429: wait, then
continue automatically.

## Boundary

- Opt-in, default off. The existing rule that errors need an explicit resume (so a
  watch loop cannot silently retry paid work) stays the default.
- Only HTTP 429 responses qualify, plus (scope addition, below) HTTP 503 whose JSON
  error status is `UNAVAILABLE`. Other 5xx, transport failures, authentication, billing
  and other 4xx responses, invalid model output and budget exhaustion keep the
  existing blocked/budget behavior.
- No change to scientific stages, prompts, workflow edges or provider fallback
  ordering. Stored run configurations without the new section load with it disabled.
- Files owned: `providers.py` (ProviderError fields, 429 hint parsing), `agents.py`
  (flag survives fallback/cooldown), `config.py` (`QuotaWaitConfig`), `contracts.py`
  (RunState wait fields), new `quota_wait.py` (policy helpers and status text),
  `engine.py` (step/run/resume), `settings.py` (one setup field), `cli`/
  `terminal_style.py`, `tui.py`, `static/app.js` (status text), docs, new tests.

## Design

- `ResearchConfig.quota_wait`: `enabled=False`, `initial_seconds=60`,
  `max_interval_seconds=3600`, `max_total_seconds=93600` (26 h, covers a daily reset).
- `ProviderError.rate_limited` / `retry_after_seconds` / `model`: set only for HTTP
  429 after the provider's own retries. Hint from `Retry-After` (seconds or HTTP date)
  or Google `error.details[].retryDelay` (`"37s"`), the larger one.
- Fallback: the error raised after all routes fail (or are cooling down) is marked
  rate limited only when every route's last failure was a 429.
- Engine: on a rate-limited ProviderError (searched through `__cause__`/unsuppressed
  `__context__`) with the option enabled, status `waiting` (reused; it already means
  "automatic wait, run loop polls") plus `RunState.quota_wait_until`,
  `quota_wait_attempts`, `quota_wait_seconds`. Event `provider_quota_wait`. Delay
  `min(max_interval, max(hint, initial * 2**attempts))`; if cumulative scheduled
  wait would exceed `max_total_seconds`, the existing `blocked` + `stage_error` path
  is used with an explicit note and the counters reset (history stays in events).
- `step` returns before any configuration resolution, runner creation or model call
  while now < `quota_wait_until`, but still enforces pause and `wall_seconds`.
  Success clears the counters. `run` sleeps in chunks of at most 10 s until the
  not-before time, the wall deadline or a pause request. Polling sleeps do not count
  as steps.
- `resume` keeps a future not-before time (status `waiting`), so resume never probes
  early; pause/resume remain honored.

## Scope addition (coordinator, 2026-10-07)

Live evidence: the Gemini free tier returns HTTP 503 with body error status
`UNAVAILABLE` ("This model is currently experiencing high demand...") for long
stretches. That specific overload response is unbilled and transient, so it is treated
as capacity-limited exactly like 429 (`providers.overloaded`). A 503 without that
status, 500, 502 and other 5xx still never trigger quota waiting.

## Acceptance

- Provider: 429 sets `rate_limited` and parses both hints; 503 `UNAVAILABLE` sets it;
  other 5xx, 4xx and transport failures do not.
- Fallback: all-429 keeps the flag; mixed 429/5xx does not; cooldown-only keeps it.
- Engine: enabled → waiting with correct not-before and event; disabled → blocked
  (unchanged); no provider call before not-before; success resumes and clears the
  counters; max_total → blocked; pause honored while waiting; wall/calls caps enforced.
- Status text: `metis status`, TUI and web show
  "Waiting for provider quota; next attempt at HH:MM".
- Full CONTRIBUTING check list.

## Validation history

- First full `pytest -x` run was started in the foreground with a 600 s tool timeout,
  moved to the background and killed when the session stalled; no result was
  recorded from it. It was rerun below.
- The first call-budget engine test failed (`blocked`): a live-mode custom stage
  handler needs `behavior_identity()`, and writing the run config directly changed the
  recorded AI behavior. Fixed in the test by giving the handler an identity and using
  `Store.update_budget`; no runtime change.
- `metis settings --scope workspace set quota_wait.enabled true` is refused ("This
  scope contains only model routing and Laya settings"); the unscoped
  `metis settings set quota_wait.enabled true` works and is what the docs show.
- A busy-loop risk at exactly the wall-clock limit (step uses `elapsed > wall`) was
  avoided by sleeping until one second past the limit.

## Final validation (feature commit `31df1ad`)

Run in this worktree after `uv sync --frozen --group dev --extra evaluation`:

| Command | Result |
|---|---|
| `uv run --no-sync ruff format --check .` | 171 files already formatted |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync mypy src` | No issues in 87 source files |
| `uv run --no-sync metis validate-specs` | exit 0 |
| `uv run --no-sync pytest -q tests/test_provider_quota_wait.py` | 29 passed |
| `uv run --no-sync pytest -q` | 1122 passed, 3 skipped (382 s) |
| `node --test tests/*_ui.mjs` | 107 passed |
| `uv run --no-sync python scripts/scan_secrets.py` | Public-file scan passed |
| `metis demo` (scratch `AUTORESEARCH_HOME`) | exit 0; stage `complete`, status `completed` |

The demo is synthetic and makes no model calls. None of these checks makes a real
provider request, so live recovery from a Gemini quota reset is untested. The fidelity matrix
is unchanged: this is runtime behavior, not a scientific stage.
Independent review is pending ([record](../reviews/provider-quota-wait.md)).

## Review round 1 (findings F1–F6, fixes `531b81d`)

See [the review](../reviews/provider-quota-wait.md). F1 (stale past not-before time
caused a busy loop after a later `CodingPending`) was confirmed: the new regression test
failed with the fix temporarily reverted, then passed. F3 excludes `insufficient_quota`
429s. F2, F5 are code fixes. F4 and F6 are documentation.

| Command | Result |
|---|---|
| `uv run --no-sync pytest -q tests/test_provider_quota_wait.py` | 34 passed |
| `uv run --no-sync pytest -q` | 1127 passed, 3 skipped (355 s) |
| `uv run --no-sync ruff format --check .` / `ruff check .` | pass / pass |
| `uv run --no-sync mypy src` | No issues in 87 source files |
| `uv run --no-sync metis validate-specs` | exit 0 |
| `node --test tests/*_ui.mjs` | 107 passed |
| `uv run --no-sync python scripts/scan_secrets.py` | passed |
