# Provider quota wait review

Status: **changes requested** (one high-severity finding; the rest are small).

- Reviewer: independent review agent (Claude Code), 2026-10-07. Not the implementing agent.
- Base: `70a1840` (merge-base with `main`). Branch `codex/provider-quota-wait`, worktree
  `Metis-quota-wait`.
- Commits reviewed: `31df1ad` feat: opt-in wait for provider quota after HTTP 429;
  `3f6275b` docs: document provider quota wait and record validation.
- Plan: [provider-quota-wait](../plans/provider-quota-wait.md).
- Method: read `git diff 70a1840..codex/provider-quota-wait`, the surrounding engine, agent,
  provider, store, behavior, web and TUI code, AGENTS.md, docs/development.md,
  CONTRIBUTING.md, docs/accounting.md and VIBE.md, then ran the checks below and one scratch
  reproduction (outside the repository; nothing in the worktree was changed except this file).

## Checks run by the reviewer

| Command | Result |
|---|---|
| `uv run --no-sync pytest -q tests/test_provider_quota_wait.py tests/test_engine.py tests/test_providers.py tests/test_provider_fallback.py tests/test_provider_streaming.py tests/test_agents.py` | 128 passed |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync mypy src` | No issues in 87 source files |
| Scratch reproduction of F1 (pytest, fixtures imported from `tests/test_provider_quota_wait.py`) | Confirmed: see F1 |

The full suite, UI tests, `validate-specs`, the secret scan and the demo were not re-run by the
reviewer; the author's results are in the plan.

## Requirement checks

1. **429/503 classification and retry hints: pass, with one gap (F3).** `limited` is set only
   for HTTP 429, or HTTP 503 whose JSON `error.status` is `UNAVAILABLE` (dict or list-wrapped,
   first 4 items). 500, 502, plain 503, 4xx (`Provider request rejected`), transport errors
   and invalid output never set it. `retry_hint_seconds` takes the larger of `Retry-After`
   (seconds or HTTP date, negatives clamped to 0, non-finite values dropped) and
   `details[].retryDelay` (`"37s"`, list-wrapped bodies included). It is computed only for
   limited responses, and the flag comes only from the final attempt. Tests cover each case.
   Gap: OpenAI-style 429 `insufficient_quota` (billing) is treated as a quota wait (F3).
2. **Fallback in agents.py: pass, one small improvement possible (F5).** Single-route and
   protected routes are unchanged: they keep `recoverable=False` and do not fall back. Their
   provider `rate_limited` flag passes through unchanged, so the same model waits and is
   retried later, which is reasonable. In multi-route fallback the flag is recomputed from
   every permitted route's last failure: all must be rate limited, and a 5xx or success on a
   route clears its entry. The cooldown-only error carries the flag too. The cooldown timing
   and the order fallbacks are tried in are unchanged. Fallback attempts use `retries=0`, so
   they do no in-request sleeping.
3. **Engine step/run: fails on stale wait fields (F1); everything else passes.** The early
   return comes before `behavior.verify`, `resolved_config`, runner creation, reservation and
   handler. The test checks that the version does not change and the handler is not called.
   It runs inside the lease, after the pause and blocked checks. Wall-clock is checked before
   the not-before test, and `_sleep_for_quota` caps its sleep at the wall deadline + 1 s, so
   there is no busy loop at the limit. It sleeps in chunks of 10 s or less, checks pause each
   time, and holds no lease while sleeping. Web `server_close` pauses workers, so shutdown
   waits at most about 10 s. `max_steps` does not sleep after the final step. The `waiting`
   status is a valid existing status. Failure: quota fields are cleared only on success and on
   the generic blocked path, so they leak into `CodingPending` waits (F1).
4. **Schema and config compatibility: pass.** `RunState` and `ResearchConfig` gain defaulted
   fields, so stored runs and configs without them load with the feature disabled.
   `quota_wait` sits in the pinned behavior bundle, because configuration and the `RunState`
   schema are hashed. So a run keeps its creation-time setting, and enabling it for an
   existing run is refused as behavior drift. The docs say this ("enable the option before
   creating the run"). Any source change already changes the runtime manifest, so this branch
   adds no new compatibility break. The setting is unscoped; workspace-scope refusal is
   recorded in the plan.
5. **Accounting: pass (no double charge or leak); doc wording needs fixing (F4).** Each probe
   is an ordinary reservation, settled from `ProviderError.usage` in `_one_attempt`, exactly as
   before. Nothing is reserved while waiting. A 429/503 body without `usage` is charged the
   conservative estimate (`accrue(self._reported_usage(body, estimate))`). That is unchanged,
   but now it repeats on every probe.
6. **UI copy: pass, except stale display (F1).** "Waiting for provider quota; next attempt at
   HH:MM" names the action and time literally, as VIBE.md asks. The web view puts Slurm
   pending and errors ahead of it. The TUI and `metis status` show it only for `waiting` with a
   parseable time. But a stale past time is shown during coding waits (F1).
7. **Tests: mostly good, two gaps.** The tests exercise the real provider over
   `httpx.MockTransport`, the real fallback loop and the real engine with an injected clock.
   They do not mirror the implementation. Missing: a `CodingPending` (or other non-quota
   `waiting`) after a quota wait (F1), and a 429 `insufficient_quota` body (F3).

## Findings

### F1 — High: quota fields survive into a coding/scheduler wait, causing a busy loop and a stale status

`src/autoresearch/engine.py:348-363` lets the step continue once `now >= quota_wait_until`
but keeps the field. The `CodingPending` handler (`engine.py:416`) then sets
`status="waiting"` and does not clear it. `run()` (`engine.py:313`) sees
`waiting and quota_wait_until` and calls `_sleep_for_quota`, which returns at once because
the time has passed. It never reaches the `slurm_poll_seconds` sleep, so every step re-runs
behavior verification, config resolution and the handler's scheduler/measurement poll with no
delay. The run stays in this loop until the coding job finishes. Sources of `CodingPending`:
`coding.py:538` scheduler job, `protocol.py:203` independent measurement check.

Reproduction: handler outcomes `[limited(), CodingPending(...), CodingPending(...)...]`. Step,
advance the clock 61 s, step, then `engine.run(max_steps=5)` with `time.sleep` patched. Result:
5 more handler calls and **0 sleeps**. Status stays `waiting` with the old `quota_wait_until`.
`status_message` returns "Waiting for provider quota; next attempt at 21:05", a time already
in the past, so TUI, CLI and (when there is no `pending_job_id`) web show the wrong reason.
`attempts`/`seconds` also carry into later unrelated waits.

Fix: once the not-before has passed and the step continues, clear `state.quota_wait_until` in
memory before the `try`. Keep `attempts` and `seconds` so backoff stays continuous until a
success. As defense in depth, make `run()` branch on `moment > now` rather than on a
non-empty string, and have `status_message` (and the JS `quotaWaitMessage`) return empty once
the time has passed. Add a regression test for exactly this sequence.

### F2 — Low: the `provider_quota_wait` event reports the possibly mutated stage

`engine.py:479` uses `state.stage.value`, but `stage_error` uses `previous.value`. If a handler
moved `state.stage` before the provider call failed, the event names the wrong stage.
Persisting mutated in-memory state on failure is older behavior, and the blocked path does it
too. Quota waiting makes the retry automatic, though, so record `previous` (pass it into
`_schedule_quota_wait`) for consistency. Consider noting that partial handler mutations are
retried automatically.

### F3 — Medium: billing exhaustion returned as HTTP 429 is treated as a quota wait

OpenAI-compatible providers return 429 with `error.code`/`error.type == "insufficient_quota"`
when credit or billing is exhausted. `providers.py:437` treats every 429 as limited, so such
a run waits up to 26 h and makes about 30 probes instead of stopping. That contradicts the
plan boundary and `docs/usage.md:220` ("billing errors ... still stop the run"). Fix: in the
limited test, exclude bodies whose `error.code` or `error.type` is `insufficient_quota`
(dict or list-wrapped), add a test, or else correct the docs.

### F4 — Low: the docs understate what probes cost against the run budget

`docs/usage.md:232` says providers usually do not bill rejected 429/overload requests. That is
true, but Metis's own ledger charges each response with no `usage` the conservative estimate:
input bound plus `max_output_tokens` at long-context rates. With non-zero configured prices,
a long wait can therefore use up `budget.usd` with estimated charges. Add one sentence saying
so; free-tier pricing at 0 is unaffected. No code change is needed; this is the documented
conservative rule.

### F5 — Low: `min(hints)` can over-wait when one limited route gave no hint

`agents.py:368-374`: suppose route A hinted 3600 s and route B gave no hint. Then `min` is
3600 and `next_delay` waits an hour, although B might accept a request after the 60 s
backoff. Fix: if any limited route has no hint, use `None`.

### F6 — Low (documentation): the in-request retry change applies even when the option is off

`providers.py` now honours `retryDelay` and HTTP-date `Retry-After` for in-request retries on
429/503-UNAVAILABLE, capped at 30 s, whatever `quota_wait.enabled` is set to. Single-model
pools on Gemini may now sleep up to 30 s per retry instead of 8 s or less. This is acceptable
and respects the provider, but mention it in `docs/model-routing.md`, which describes retry
behavior.

## Author's open questions

- **Resume does not force an early retry:** agree. It keeps the "no probe before
  not-before" promise. A user who knows the quota has been restored waits at most
  `max_interval_seconds`. A later explicit "Try now" action would be a separate,
  deliberate feature.
- **Waiting counts toward the wall budget and elapsed timers:** agree. It is consistent with
  `budget.wall_seconds` ("Measured from run creation, including paused time"), and it is
  documented.
- **Event stage field:** use the pre-step stage; see F2.
- **An active driver is needed:** acceptable and documented. With no driver the run stays
  `waiting`, and Resume or Start keeps the schedule. No daemon is needed.
- **In-request retry honours retryDelay (capped 30 s):** acceptable; document it (F6).

## Verdict

**Changes requested.** Fix F1 and add its regression test before merging. F3 should be fixed
or the docs corrected. F2, F4, F5 and F6 are small and can go in the same follow-up commit.
The design, the opt-in default, the classification boundaries, accounting, schema
compatibility, pause/wall handling and the tests are otherwise sound. As the plan says,
nothing here shows a live recovery after a real Gemini quota reset.

## Resolution

Pending; the author records fixes and re-validation here.

## Author resolution

Fixes are in `531b81d` (code and tests) and the following documentation commit. The
reviewer's text above is unchanged. This is the author's account, not a re-review.

- **F1:** `Engine.step` clears `quota_wait_until` once the not-before time has passed and
  the step proceeds. Attempt and total counters persist until a successful step.
  `run()` uses the quota sleep only for a future time. Python `status_message` and JS
  `quotaWaitMessage` return empty for an elapsed time. New regression test
  `test_elapsed_wait_then_coding_pending_does_not_busy_loop`: a 429, then the wait
  elapses, then `CodingPending` three times. It checks that `run(max_steps=3)` makes 3
  bounded sleeps, no stale timestamp and no status text. With the fix temporarily reverted, it failed
  (stale timestamp kept). The web UI test now also checks that a past time shows no notice.
- **F3:** `providers.billing_exhausted` returns True for an error `code` or `type` of
  `insufficient_quota`, and such a 429 is not rate limited
  (`test_openai_insufficient_quota_429_is_billing_not_a_wait`, both fields). Documented in
  `docs/usage.md`.
- **F2:** the `provider_quota_wait` payload `stage` is the stage the step started in
  (`test_quota_wait_event_records_the_stage_that_failed`).
- **F4:** `docs/usage.md` says that unreported-usage attempts are charged the
  conservative estimate, so long waits can use `budget.usd`.
- **F5:** the fallback hint is `None` if any limited route lacks a hint
  (`test_fallback_hint_is_unknown_when_any_limited_route_has_none`).
- **F6:** `docs/model-routing.md` states that in-request retries honour `Retry-After` and
  `retryDelay`, capped at 30 s, whatever the option is set to.

Re-validation: focused suite 34 passed; full pytest 1127 passed, 3 skipped; ruff
format/check, mypy (87 files), validate-specs, node UI (107) and the secret scan all pass.
An independent check of these fixes is still needed before merge.

## Re-review

- Reviewer: the same independent review agent, 2026-10-07. Reviewed `git diff 3f6275b..e09dc4a`:
  fix `531b81d` and docs `e09dc4a`.
- Checks run by the reviewer on `e09dc4a`:

| Command | Result |
|---|---|
| Original F1 scratch reproduction (unchanged script) | `quota_wait_until` cleared; status text empty; `run(max_steps=5)` slept five times (10 s each, the ordinary poll) instead of none |
| `uv run --no-sync pytest -q tests/test_provider_quota_wait.py tests/test_engine.py tests/test_providers.py tests/test_provider_fallback.py tests/test_provider_streaming.py tests/test_agents.py` | 133 passed (128 before + 5 new) |
| `uv run --no-sync ruff check .` / `ruff format --check .` | All checks passed / 171 files already formatted |
| `uv run --no-sync mypy src` | No issues in 87 source files |
| `node --test tests/test_web_ui.mjs` | 100 passed |

Per finding:

- **F1: resolved.** `engine.py` clears `quota_wait_until` in memory once the not-before time
  has passed and before the stage runs. Every later save, including `coding_pending`,
  therefore persists the cleared value, while attempts and total time persist until a success.
  `run()` uses the quota sleep only when the parsed time is still in the future; otherwise it
  uses the ordinary poll sleep. Python `status_message` and JS `quotaWaitMessage` return empty
  for an elapsed time. `test_elapsed_wait_then_coding_pending_does_not_busy_loop` would fail
  on the old code, which made zero sleeps (it asserts 3 bounded sleeps and an empty
  timestamp), so it exercises the bug rather than mirroring the fix. No regression found: a
  future wait still returns before any reservation, and a non-quota failure still blocks.
- **F3: resolved.** `billing_exhausted` matches `insufficient_quota` in `error.code` or
  `error.type` (dict or list-wrapped, through the shared `_errors`), and such a 429 is not
  rate limited. The parametrised test covers both fields and would fail on the old code.
  `overloaded` behaves the same after the refactor (its existing tests pass).
- **F2: resolved.** `_schedule_quota_wait` receives `previous`. The new test mutates
  `state.stage` before raising and asserts that the event names the original stage; it would
  fail on the old code.
- **F5: resolved.** The hint is `None` when any limited route lacks one, and when not
  limited `last_error.retry_after_seconds` is reset to `None`. The fixture sends
  `retry-after: 90` on the other routes, so the old `min()` would have returned 90 and the
  test discriminates. Minor: the test sets the private `_rate_limited` dict directly. That is
  acceptable for a unit of fallback logic and not worth a change.
- **F4: resolved.** `docs/usage.md` now says that attempts with no reported usage are charged
  the conservative estimate and can use part of `budget.usd`. This matches
  `providers._reported_usage`.
- **F6: resolved.** `docs/model-routing.md` states that in-request retries honour
  `Retry-After` and `retryDelay`, capped at 30 s, whatever the option is set to. This matches
  `providers.py`.

The full pytest suite, `validate-specs` and the secret scan were not re-run by the reviewer.
The author's results are above. As before, no live provider recovery has been demonstrated.

**Re-review verdict: approve.** All six findings are fixed and the regression tests
discriminate. No new issues were found.
