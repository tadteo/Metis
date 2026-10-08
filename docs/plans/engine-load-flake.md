# Intermittent `blocked` demo runs during full test runs

Base: `d9357f3`. Branch: `codex/engine-load-flake`. Status: implemented; independent review recorded
in [the review](../reviews/engine-load-flake.md).

## Source requirement

`tests/test_engine.py::test_failed_candidates_feed_all_rounds_and_do_not_create_paper` intermittently
ended with run status `blocked` instead of `failed` during full `pytest` runs on
`codex/novelty-retrieval-queries` and `codex/model-selection` (2026-10-07/08). Once,
`test_complete_real_experiment_workflow_and_resume` failed in the same run. Both passed alone. The
suspected cause was heavy concurrent CPU load. Find the timing-dependent cause, fix it or make the
test deterministic without weakening it, and add a regression test that forces the condition.

## Investigation (all attempts retained)

1. **CPU load alone did not reproduce it.** 12 parallel copies of the test body ran 3 times each,
   alongside 8 busy-loop processes (load average about 48). Result: 36/36 `failed` as expected, at
   about 60 s per run instead of 20 s.
2. **Concurrent full suites did not reproduce it.** Four full `pytest -x` runs ran in parallel with 4
   busy loops. The test passed in all four. Two runs stopped on an unrelated load flake,
   `tests/test_quota_aware_routing.py::test_all_exhausted_waits_until_earliest_reset_without_probing`
   (`assert 3600.0 < 3600`, line 300). It is out of scope here and reported separately.
3. **Code review of timing paths.** Wall-clock budgets are 7 days (run) and 4 h (coding), and the
   experiment timeout is 3600 s. Leases use a PID-liveness check, not a timeout. None of these can
   expire in a 60 s demo run.
4. **Recorded failures.** The failing assertion does not print `result.error`. The agent
   transcripts of the three failing suite runs show that `src/autoresearch` files were **edited
   while each suite was running**:
   - novelty-queries: suite started 19:44:29; `src/autoresearch/literature.py` rewritten 19:46:03.
     Result: `1 failed, 1146 passed`.
   - model-selection: suite started 08:37:28; `model_selection.py`, `setup.py` and `static/app.js`
     edited from 08:37:45 on. Result: `5 failed, 1215 passed`, including both demo tests.
   - model-selection: suite started 08:46:23; `model_selection.py` edited 08:49:53.
     Result: `1 failed`.
5. **Deterministic reproduction.** One new `.py` file was written under `src/autoresearch` during
   the `RejectExperiments` demo run. Result: `status=blocked`, `stage=generate_ideas`,
   `error="ValueError: AI behavior changed since this run was created. ..."`.

## Root cause

`Engine.step` calls `behavior.verify` on every step. `verify` recomputes
`behavior.runtime_manifest()`, a SHA-256 of every `.py/.json/.md/.txt` file under the installed
package. It compares the result with the bundle pinned at `create`. This is intended provenance: a
run must not continue under changed executable source, and lazily imported modules and data files
are read from disk. A test suite run from an editable checkout that someone is editing therefore
blocks any demo run whose 20–60 s lifetime spans the edit. CPU load only widened the window. Two
gaps hid the cause:

- The error said behavior changed but not *what* changed.
- A green or red suite run against a mutating checkout was reported as ordinary evidence.

## Implementation boundary

- `src/autoresearch/behavior.py`: `verify` names the changed sections of the bundle, and the
  added, removed or modified runtime source paths (capped). This uses a shared `drift` helper.
  Comparison and refusal semantics are unchanged: any digest difference still blocks.
- `tests/conftest.py`: a session guard snapshots `runtime_manifest()` at session start and
  compares it at session end. If package source changed, the session fails and names the files,
  because results from mixed code versions are not evidence.
- No change to engine control flow, budgets or the demo provider.

## Acceptance criteria

- Forcing a source change partway through the `RejectExperiments` demo run yields `blocked`, with
  an error naming the changed file. Restoring the source and resuming completes the run with the
  original `failed` / `no_successful_full_benchmark_idea` outcome and 8 candidate decisions.
- `behavior.drift` reports added, removed and modified files and changed bundle sections.
  Identical bundles report no drift.
- The session guard fails a session whose package source changed, and leaves an unchanged
  session's exit status alone.
- The existing `tests/test_behavior.py` refusal tests still pass unchanged.
- Full CI command set (`ruff format --check`, `ruff check`, `mypy src`, `pytest`) passes.
