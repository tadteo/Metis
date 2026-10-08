# Review: quota-aware routing

- Reviewer: independent review agent (Claude Opus 5.5), requested by the coordinator
- Branch: `codex/quota-aware-routing` (worktree `Metis-quota-routing`)
- Base: `07db7c5` (main; main has not moved since)
- Commits reviewed: `767aaba` feat, `c2d1662` docs
- Scope: `git diff 07db7c5..codex/quota-aware-routing` (15 files), plan
  `docs/plans/quota-aware-routing.md`, `docs/model-routing.md`, `docs/usage.md`,
  `docs/accounting.md`. No network calls were made.

## Checks run by the reviewer

| Command | Result |
|---|---|
| `uv run --no-sync python -m pytest -q tests/test_quota_aware_routing.py tests/test_provider_quota_wait.py tests/test_provider_fallback.py tests/test_agents.py tests/test_engine.py tests/test_writer_supervision.py` | 133 passed (82 s) |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync mypy src` | No issues in 87 source files |
| `git merge-tree --write-tree main codex/quota-aware-routing` | clean (main == base) |
| `git merge-tree --write-tree codex/provider-presets codex/quota-aware-routing` | clean; `codex/provider-presets` currently has no commits beyond `07db7c5`, so its limits metadata interface does not exist yet |

The full suite, UI tests and demo were not re-run by the reviewer (recorded by the author
in the plan).

## What was verified as correct

- 429 classification (`providers.py:120-208`): RetryInfo/Retry-After hint is the max of
  advertised values; > 60 s, a daily-or-longer QuotaFailure quota id, or
  `x-ratelimit-remaining-*: 0` with reset > 60 s is long; long with no reset uses 3600 s.
  Long raises after one attempt with `usage=total`, `recoverable=True`, `rate_limited=True`
  and an absolute `quota_exhausted_until`. 503 `UNAVAILABLE` overload is untouched (the
  long-window branch requires `status_code == 429`). `insufficient_quota` billing 429s
  are still excluded before classification.
- A per-minute 429 misclassified as long because of a long Retry-After is low impact:
  the exhaustion lasts only the advertised delay, and fallback/quota wait take over.
- Exhaustion key `base_url|model|api_key_env` (`agents.py:quota_key`, via
  `model_inventory.identity`) matches the fallback identity, so skipping and slot
  freeing agree. Records are written under a lock into both the runner and `RunState`;
  the engine merges runner records and prunes expired ones before every save path
  (success, workflow violation, coding pending, budget, generic exception/quota wait).
  Restarts read the persisted field; old runs load with the empty default.
- `research_view` and the official-writer fingerprint exclude the field; cache keys are
  unchanged (`memory.py:21`, `paper_orchestra.py:790`, test at
  `tests/test_quota_aware_routing.py:448`). The `test_writer_supervision.py` change
  mirrors the production exclusion and is justified.
- Fallback keeps the frozen pool and cost order; exhausted models do not occupy the two
  alternative slots; an exhausted primary is skipped without a request and the
  `provider_fallback` event names the reason. The existing 60 s cooldown still applies
  to the failing model.
- Quota wait: when every usable route is exhausted, `quota_exhausted_until` is the
  earliest reset over routes and pool; `reset_delay` floors at 1 s and caps at
  `max_interval_seconds`; a capped wake-up emits `model_quota_skipped` and sends no
  request; wall budget (`max_total_seconds`) still bounds total waiting.
- Protected routes are never swapped; exhausted → no request, non-recoverable,
  rate-limited → wait if enabled, else blocked. This matches the previous behavior for
  a protected 429 (it was already non-recoverable and rate-limited).
- Size guard: inactive without metadata; skipped models get an event and no
  reservation; when none fits the run blocks with a non-rate-limited error.
- Accounting: reservations are made per attempt; long-window errors settle once with
  the accumulated usage; skipped and oversized calls reserve nothing. The probe test
  checks the 1/9 reservation and the charge.
- Fixture change `Retry-After 90 → 45` in `tests/test_provider_quota_wait.py` is
  required by the new rule (90 s is now long) and keeps that suite on the short path.

## Findings

### M1 (medium) — "single-attempt probe" applies to the whole stage, not the first call

`engine.py:382,404`, `agents.py:102,469`. `runner.single_attempt` is set for every
stage entered with `quota_wait_attempts > 0` and is never cleared, so every
single-route call in that stage (one-model pools — the free-tier case — protected
routes, legacy configs) runs with `retries=0`. The docs say only "the first model
call after a wait" is a probe (`docs/usage.md`, `docs/model-routing.md`,
`docs/accounting.md`). In a long stage, a later per-minute 429 then fails at once and
schedules another quota wait (with growing backoff) instead of the bounded 30 s retry,
and a transient 5xx/network error makes the run block instead of retrying.
Fix: consume the flag once, under the lock, at the first provider dispatch, or clear
it after the first completed attempt. Add a test with two calls in one stage after a
wait: the first gets one attempt and the second gets `retries + 1`.

### M2 (medium) — external command roles are blocked by an exhausted model they never call

`agents.py:438-469`. Roles in `role_commands` are protected, and the protected path
checks `_exhausted_until(state, route.provider)` before `_one_attempt`. External
commands go through `_command` and never call that provider
(`agents.py:749-752`). If the role's nominal route resolves to an exhausted model
(for example the default Gemini model), the command is refused with a quota error and
the run waits or blocks. This is a regression for external commands. Fix: skip the
exhaustion check when `role` or `original_role` is in `role_commands` (the size guard
already skips them). Add a test.

### M3 (low–medium) — a daily QuotaFailure with a short RetryInfo trusts the short delay

`providers.py:205-207`. If a daily quota id is present, the window is long, but
`reset` stays the advertised hint. If Gemini sends a per-day violation with a short
`retryDelay` (the observed run had about 85101 s, but the delay may reflect the
per-minute bucket), the model is "exhausted" for only a few seconds. Quota wait then
probes about every `retryDelay` until `max_total_seconds`. This contradicts the goal
of not spending requests before the reset. Fix: when `daily` is non-empty and
`reset < SHORT_WINDOW_SECONDS`, use `UNKNOWN_RESET_SECONDS` (or at least more than
the short window). Add a test.

### L1 (low) — single-route long 429 does not report the earliest pool reset

`agents.py:460-475`. When the only usable route gets a fresh daily 429, the error
carries that model's reset (~24 h). Other pool models already exhausted (and excluded
from `routes`) may reset sooner. When `max_interval_seconds` is large, the wait
overshoots the earliest reset. Fix: if the error has `quota_exhausted_until`, replace
it (and `retry_after_seconds`) with the minimum over the error and
`pool_exhausted.values()`.

### L2 (low) — the "excluded from prompts" claim does not cover the writer's raw materials

`paper_orchestra.py:169` writes the full `state.model_dump()` (including
`model_quota_exhausted`) to `raw_materials/state.json`, which the official writer
reads. This is operational metadata (model names, quota ids, reset times), not
scientific content. The same already happens for `quota_wait_*`. Fix: exclude the
field there too, or narrow the claim in `docs/model-routing.md`.

### L3 (low) — no operator override for a persisted exhaustion

The key uses the key *reference* (`api_key_env`), not the key value. After the
operator rotates the key or upgrades the tier, the run still skips the model for up
to the recorded reset (~24 h). Pausing or resuming does not clear it. Fix: clear
`model_quota_exhausted` on an explicit Resume or with a CLI flag, or document the
limitation.

### L4 (low) — test coverage notes

- After the 90 → 45 change, `tests/test_provider_quota_wait.py` no longer checks the
  "provider hint exceeds initial wait" branch of `next_delay` for a 429. Check that
  another test covers it, or add one with a hint above `initial_interval_seconds` and
  at most 60 s.
- No test covers M1 (several calls after a probe), M2 (command role with an exhausted
  nominal model), M3 (daily id with a short `retryDelay`), or `parallelism > 1` with a
  shared exhausted model. Under `parallelism > 1`, concurrent agents can each spend one
  request before the first records exhaustion. This is bounded and acceptable, but it
  is undocumented.

### Info

- Exhaustion is per run: concurrent runs that share a key each spend one request per
  model to learn the exhaustion. This is acceptable and matches the lease model.
- The bytes/4 estimate (`agents.py:_guard_size`) uses UTF-8 bytes and ignores output
  tokens. It usually underestimates (CJK, code), so it errs toward sending. Prompts
  that embed `json.dumps` with `ensure_ascii` can overestimate non-ASCII text by about
  1.5×. The guard only acts when declared metadata exists. Keep it documented as a
  heuristic.
- `model_limits` field names and aliases are speculative until `codex/provider-presets`
  lands. Agree the names before that branch merges.
- Adding a field to `RunState` blocks downgrade if the model forbids extra fields.
  Older code cannot load newer state. This is expected and does not block merge.

## Verdict

**Changes requested (minor).** The core design is sound and matches the plan:
classification, persisted exhaustion, frozen-pool fallback, earliest-reset waiting,
protected-route semantics and accounting. The targeted tests, ruff and mypy pass, and
the branch merges cleanly into main. Fix M1 and M2 before merge: each is a behavioral
regression outside the free-tier happy path. Fix M3 or record it explicitly as an
accepted risk with a test. L1–L4 can be fixed now or recorded in the plan's open
risks.

## Author resolution

All findings were addressed in the follow-up commit on `codex/quota-aware-routing`
(recorded in [the plan](../plans/quota-aware-routing.md#review-round-1)).

- M1: `AgentRunner._take_single_attempt()` consumes the probe flag at the first dispatch
  (single-route or fallback loop). Test `test_probe_flag_is_one_shot`: the first call
  makes one request, the next call in the same runner uses the configured retries.
- M2: the single-route exhaustion check is skipped for `role_commands` roles (command
  roles are always protected, so they never take the fallback loop). Test
  `test_command_role_ignores_exhausted_nominal_model`.
- M3: a daily `QuotaFailure` id now waits at least `UNKNOWN_RESET_SECONDS` even with a
  shorter `retryDelay`. Test `test_daily_quota_with_short_retry_delay_waits_at_least_reprobe_delay`.
- L1: a fresh long 429 on the only usable route reports the minimum over its reset and
  the pool's recorded resets. Test `test_single_route_daily_429_reports_earliest_pool_reset`.
- L2: `model_quota_exhausted` is excluded from `raw_materials/state.json`. The
  `quota_wait_*` fields are left unchanged (removing them would change existing prompts,
  cache keys and writer fingerprints); `docs/model-routing.md` now says so.
- L3: `metis resume RUN --clear-quota` (`Engine.resume(..., clear_quota=True)`) clears
  records and any scheduled wait, recording `model_quota_cleared`. Documented in
  `docs/usage.md` and `docs/model-routing.md`. Test `test_resume_can_clear_recorded_exhaustion`.
- L4: added `test_parallel_agents_record_one_exhaustion` (bounded duplicate requests,
  one record; documented) and `test_short_window_hint_above_initial_wait_is_honored`.
- Field names `limits.context_window_tokens` / `limits.tokens_per_minute` are kept as
  agreed with `codex/provider-presets`.

## Re-review (round 2)

- Reviewer: the same independent review agent (Claude Opus 5.5)
- Scope: `git diff c2d1662..15f563c` (`b460402` review, `aa24a62` fix, `15f563c` docs)
- No network calls were made.

### Checks

| Command | Result |
|---|---|
| Targeted pytest (6 suites, as in round 1) | 140 passed (82 s) |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync mypy src` | No issues in 87 source files |
| New `tests/test_quota_aware_routing.py` (from `aa24a62`) run against the `c2d1662` source (`PYTHONPATH` set to an extracted copy of the old `src`) | 5 failed, 21 passed |

The 5 tests that fail on the old code are `test_probe_flag_is_one_shot`,
`test_command_role_ignores_exhausted_nominal_model`,
`test_daily_quota_with_short_retry_delay_waits_at_least_reprobe_delay`,
`test_single_route_daily_429_reports_earliest_pool_reset` and
`test_resume_can_clear_recorded_exhaustion`. Each fails because of the behavior under
test:

- the probe flag stays True;
- `ProviderError` "quota exhausted ... route is fixed" is raised for a command role;
- `retry_after` is 10 s instead of 3600 s;
- the reset is about 24 h instead of the pool's earlier reset;
- `resume()` has no `clear_quota` argument.

So these tests discriminate. `test_parallel_agents_record_one_exhaustion` and
`test_short_window_hint_above_initial_wait_is_honored` also pass on the old code. That
is expected: they add coverage (L4) rather than check a regression.

### Findings

- **M1, resolved.** `agents.py:_take_single_attempt` swaps the flag under the lock. It
  is consumed at the first dispatch on the single-route path and in the fallback loop
  (fallback attempts were already single-attempt). Residual (info): a cache hit inside
  `_one_attempt` also consumes the flag. The next real request then uses the configured
  retries. This is harmless, because a daily 429 still stops after one attempt.
- **M2, resolved.** The exhaustion check is skipped when
  `role in self.config.role_commands`. This is the same predicate that routes to
  `_command`. Command roles are always protected, so they never reach the fallback loop.
- **M3, resolved.** `providers.py:206-210`: when a daily id is present, the reset is
  `max(hint, UNKNOWN_RESET_SECONDS)`. A daily id with a long `retryDelay` (85101 s)
  keeps its advertised delay.
- **L1, resolved.** A single-route `ProviderError` with `quota_exhausted_until` now
  takes the minimum over its own reset and `pool_exhausted`. `retry_after_seconds` is
  recomputed. Only non-protected routes are affected, because `pool_exhausted` is empty
  for protected routes.
- **L2, resolved; writer fingerprints are unchanged.** The fingerprint hashes `payload`
  (`paper_orchestra.py:790`), which already excluded the field. Only the
  `raw_materials/state.json` content changes. That file is written only when `job.json`
  is absent, so existing writer workspaces are not rewritten. The `quota_wait_*` leak is
  kept on purpose and documented.
- **L3, resolved, with no bypass of budgets, pause or leases.** `Engine.resume`:
  - It clears the records and `quota_wait_until` inside the existing `store.lease`, and
    saves a `model_quota_cleared` event.
  - It does not reset `quota_wait_seconds` or `quota_wait_attempts`. The total wait
    budget therefore still applies, and the next dispatch is still a one-attempt probe.
  - Cost budgets and reservations are untouched.
  - The un-pause comes from the existing resume semantics, not from the new flag.
  - The flag is opt-in from the CLI only; the web resume path is unchanged.
  - Clearing a scheduled wait lets the next step call the provider right away. This is
    the documented intent of an explicit operator action.
- **L4, resolved.** The coverage tests were added.

### Verdict

**Approved.** All round-1 findings are resolved and the new tests discriminate.
Targeted tests, ruff and mypy pass. Before merge, re-run the full suite and the
`merge-tree` check against main and `codex/provider-presets`. Round 2 did not re-run
either.
