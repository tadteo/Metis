# Development and continuation

The first commit, `6936a17` (`chore: import existing prototype`), imports all existing code once.
It includes unfinished integrations. It does not reconstruct a fictional feature history.

## One task, one branch

1. Inspect `git status`, `git log`, and `docs/plans/`. Identify ongoing work before editing.
2. Write a focused task plan with the source requirement, implementation boundary, acceptance
   criteria and regression/behavioral checks. Keep the plan with its task branch.
3. Create an isolated worktree and a `codex/` branch from the current integration base. Parallel
   agents must use different worktrees. Tell the coordinator which files/interfaces you own.
4. Implement one coherent change. Preserve other work. Update tests alongside the behavior;
   reproduce a bug before fixing it where practical.
5. Run focused tests, then the relevant repository checks in `CONTRIBUTING.md`. Use the branch's
   source when sharing an interpreter: `PYTHONPATH=src /path/to/venv/bin/pytest ...`.
6. Request review from another agent or person against the recorded base. The reviewer checks
   scientific requirements, correctness, regressions, provenance, and documented standards.
   Record actionable findings and their resolution under `docs/reviews/`. Do not self-certify
   an independent review. A passing model review does not replace deterministic checks.
7. Make small Conventional Commits (`fix:`, `feat:`, `test:`, `refactor:`, `docs:`, `chore:`).
   Stage only the task's files. Keep unrelated changes separate and preserve real chronology.
8. Merge only after review and tests pass. Re-run affected checks after resolving conflicts.
   Keep `main` usable; unfinished work remains on its branch. Prefer merge commits so branch
   boundaries and integration evidence remain visible. Never rewrite the import as fake history.

A task is complete when implementation, tests, independent review, commits, documentation and
behavioral evidence are all present. Report blocked external evaluations separately from implemented
capability. Record the exact reason; unavailable credentials do not mean a component is missing.

## Scientific acceptance gates

Ordinary CI runs without paid model calls and includes the following invariant suites:

- `tests/test_architecture.py`: live-stage specialist dispatch and reviewer coverage gates.
- `tests/test_coding.py`: real repository editing, executable feedback, failure and resumption.
- `tests/test_fidelity.py`: scientific rejection, refinement, comparison, re-entry and seed reruns.
- `tests/test_literature.py`, `tests/test_review.py`: retrieval provenance and published review prompts.
- `tests/test_execution.py`, `tests/test_store_security.py`: immutable protocol and runtime boundaries.

Add new regression suites to ordinary pytest discovery rather than running them only by hand.
The CI workflow is `.github/workflows/ci.yml`; its commands are the source of truth for release checks.
Live evaluations must identify upstream revisions, models, protocol, all attempts, costs, failures
and output hashes. Keep private runtime data out of Git. Publish only explicitly public fixtures and
redacted evidence summaries. A scripted provider validates control flow, not autonomous capability.

## Handoff and persisted state

A future agent should use, in order:

1. Git history/status for implemented and unfinished changes.
2. The task plan and review record for decisions, tests run, findings and remaining external needs.
3. `docs/fidelity.md` for published behavior → implementation → commits → evidence → remaining gap.
4. The configured private Store for `RunState`, events, usage reservations, coding checkpoints,
   command receipts and versioned artifacts. See `docs/reproducibility.md` before resuming work.

Never infer success from a final filename or a model's summary. Inspect receipts and evidence
hashes. An uncertain interrupted execution must be reconciled explicitly. New configuration does
not silently replace a stored run's configuration. Resume through the normal engine/CLI so leases,
budgets and state-version checks remain effective.

## Current coordination boundary

Two older chats continued writing in the original checkout when this repair began. Their work was
included in the import as it existed at that moment; subsequent edits remain visible in Git status.
The repair work uses isolated branches. Account for those outstanding changes explicitly before
merging; preserve them and do not attribute unreviewed concurrent code to reviewed task commits.
