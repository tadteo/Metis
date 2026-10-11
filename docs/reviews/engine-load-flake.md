# Engine demo-run flake review

Base: `d9357f3`; reviewed head: `83bb027`. Branch: `codex/engine-load-flake`.
Independent reviewer: a separate review agent; implementation author: the fixing agent.
Plan: [engine-load-flake](../plans/engine-load-flake.md).

**Verdict:** approve after the should-fix items. No blocking defects.

The reviewer independently confirmed that no other timing path can produce `blocked` in a 20–60 s
demo run:

- Wall-clock budgets are 7 days for the run and 4 h for coding.
- The 3600 s experiment timeout governs the process kill waits.
- Lease conflicts raise outside the step's `try`, so they never become `blocked`.
- A 30 s SQLite lock inside one test's private store is implausible.
- Quota sleeps lead to `waiting`, never `blocked`.

The reviewer also checked `drift`. It emits only top-level bundle keys and package-relative paths,
never prompt or configuration values. With a secret prompt override, the error read
`changed: agents; configuration; prompts`. The worst case is about 750 characters, under the
2000-character cut in `engine.py`, and still redacted. `verify` still refuses any digest change.

Reviewer validation:

- Focused suites: 31 passed.
- One full `-x` run: 1246 passed, 4 skipped. The guard did not fire, so no test writes into the
  package.
- Ruff: clean.

## Findings and resolutions

1. **Should-fix: the guard missed edits under `src/autoresearch/specs/`.** Those files are pinned
   through the catalog, not `runtime_manifest()`.
   - Resolved: the guard now hashes every package file (`package_manifest`).
   - Regression: `test_spec_edit_is_caught_and_more_specific_status_is_kept`.
2. **Should-fix: the guard overwrote any exit status with 1.**
   - Resolved: it now escalates only from `OK` or `NO_TESTS_COLLECTED`.
   - Regression: the same test checks that an interrupted session keeps exit status 2.
3. **Should-fix: the plan linked a review record that did not exist yet.**
   - Resolved: this file now exists, and the plan states the status accurately.
4. **Nit: the exact-count trigger in the regression test could race with concurrent panel calls.**
   - Resolved: the test now uses a threshold with a one-shot flag. A first attempt with only a
     threshold re-applied the edit after resume and failed (`blocked` again). That failure is
     recorded here.
5. **Nit: the resume half omitted `round == 3`.**
   - Resolved: the assertion is added.
6. **Nit: an edit that is reverted before the session ends passes the guard.**
   - Accepted: the affected tests still fail with the changed file named.
7. **Nit: `from source_guard import ...` depends on the default `prepend` import mode.**
   - Accepted: this matches the repository configuration.
8. **Nit: `docs/development.md` does not list `tests/test_source_guard.py`.**
   - Not applied: that list names the scientific invariant suites. This guard is test
     infrastructure collected by ordinary discovery.
