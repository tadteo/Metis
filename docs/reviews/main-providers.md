# Review: main paid providers and the native Anthropic adapter

Branch `codex/main-providers`, base `7c34a8d`. Reviewer: an independent agent, read-only.
It did not author the change. Its scope was the task brief and
[the plan](../plans/main-providers.md). Model selection profiles were out of scope after
the coordinator's scope change.

## First review (commits `b5f36d5`..`f0980dc`)

There were no blockers. The reviewer ran focused tests, the full suite (1294 passed, 4 skipped),
mypy and ruff. It also ran its own probe tests against the real SDK through an `httpx2` mock
transport.

| # | Severity | Finding | Resolution (`81db518`, `f69bffe`) |
|---|---|---|---|
| 1 | minor | `_stream` caught every exception, so a failing progress callback (a store write) was reported as an interrupted stream | Catch only SDK, transport and parse errors; test `test_progress_callback_errors_are_not_masked` |
| 2 | minor | A mid-stream SSE `overloaded_error` hard-failed the role, contradicting the docs | Separate branch: not resent; recoverable for `overloaded_error` and `api_error`; rate limited for overload; docs updated; test added |
| 3 | minor | The SDK still merges ambient `ANTHROPIC_CUSTOM_HEADERS` into requests | Remove those names from the client's headers; docs updated; test added |
| 4 | minor | A spend-cap 429 left the model selectable, charging another estimate each stage | `quota_exhausted_until` set to the next month start (UTC), not rate limited, so no quota wait; test added |
| 5 | minor | `retry-after` was ignored for 5xx other than 529 | Honoured on every 5xx sleep; test added |
| 6 | nit | Interrupted streams carried no response id | `details.response_id` |
| 7 | nit | Streamed successes had no request id | Taken from `stream.request_id` |
| 8 | nit | Status errors chained the SDK exception | Raised outside the handler with `from None` |
| 9 | nit | `agents._transport` duplicates `create_provider` | Kept so tests can keep patching `agents.CompatibleProvider`; docstring says to keep both in sync. Reviewer agreed. |
| 10 | nit | `CACHE_WRITE_MULTIPLIER` defined after use | Moved above `price_usage` |
| 11 | nit | OpenAI publishes a 922,000-token maximum input inside the 1,050,000 context | Preset note added; the size guard still uses the published context (open item) |
| 12 | info | `claude-haiku-5-5` is not in the brief's model list | Reviewer checked it is the current Haiku (released 2026-10-07); documented in the plan |

The reviewer verified these as correct:

- Exception ordering and per-attempt usage accrual.
- SDK request shape: no sampling keyword, `extra_body` used for Haiku 4.5, effort values,
  `max_retries=0`, no proxy and no redirects, an explicit key and base URL.
- Cost math and backward-compatible serialization.
- Unchanged CompatibleProvider defaults.
- Preset numbers, spot-checked against the cited pages.
- Lazy SDK import, with no writer image dependency.
- Writer refusal.

## Re-review

All 11 resolutions are correct, with no new blockers or majors. Focused tests (57), mypy and
ruff passed. Two new nits were fixed in the same commit:

- The mid-stream error progress event now includes `answer_chars`.
- The spend-cap message now says to run `metis resume RUN --clear-quota` after raising the cap
  (the docs say the same), instead of implying the model returns automatically.

## Evidence after resolution

The following all passed:

- `ruff format --check`, `ruff check`, `mypy src` and `metis validate-specs`.
- Full `pytest`: 1300 passed, 4 skipped.
- `node --test tests/*_ui.mjs`: 108 passed.
- `scan_secrets.py` and `metis demo` (synthetic).
- `uv build --wheel` with `tests/test_package.py`.
- Writer CI-equivalent tests: `test_writing_upstream.py` and `test_writer_recovery.py`, run with
  the hash-locked writer requirements and the pinned source `ca1b3fa`. Result: 10 passed and
  1 skipped, the skip needing `AUTORESEARCH_UPSTREAM_FIXTURE`.
- `uv lock --locked`.

No live provider request was made. These tests show request shape, control flow and
accounting. They do not show live access, research quality or parity between models.
