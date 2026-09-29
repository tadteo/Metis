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

## Integration and concurrent-work provenance

The prototype was imported honestly once in `6936a17`. Other active chats continued
editing after that import. Their later work was frozen at base
`0bdbd07e196d1aeb306d0e89811223babe2ccdb1` and retained in Git stash object
`dd5ea451520072415e742484fccbb401f00014a6`, with 118 file hashes recorded during
integration. Focused plans/reviews identify which files were inherited, independently
reviewed, corrected and committed; inherited code is not represented as newly authored
historical work. The final reconciliation evidence is [the 118-file hash accounting](evidence/inherited-integration.json) and [the independent integration review](reviews/fidelity-integration.md).
The baseline and reviewed branch commits remain intact in Git history.

Key continuation entry points are the per-component commits in the fidelity matrix,
`docs/reviews/`, `docs/plans/`, and the configured private run state. Do not depend on
temporary archive paths, prior chats, or a live agent's memory to understand behavior.
The frozen stash is historical provenance, not an instruction to overwrite current code.
Restore specific archived material only after comparing it with the reviewed version.

Before final integration, inventory every active checkout and preserve any concurrent
uncommitted edits. New work in another user's branch (including architecture refactors)
is outside this repair unless separately assigned. Do not absorb it merely because its
files share names. Ask the coordinator to resolve ownership before parallel edits;
merge reviewed tasks and record any conflict resolution and affected test results.

## Maintained architectural gates

The ordinary CI environment installs `--extra evaluation` and uses `uv run --no-sync`
thereafter. It runs the full unit/integration suite, types, formatting, browser logic,
public-file scanner and synthetic demonstration. Tests enforce claim/input binding,
negative-result preservation, ablation/rebuttal loops, review persistence, held-out
isolation, immutable artifacts, provider accounting and resumable source inspection.
A separate job checks actual pinned official writer source/SDK imports and recovery
with deterministic responses. It needs no paid credentials and does not validate
live TeX, Docker, reviewer quality or research performance.

`tests/test_fidelity_matrix.py` validates all stages, nonempty commit/evidence mappings,
actual Git ancestry, existing source/test files and named test functions, classification
consistency, synchronized package/document JSON and deterministic generated reports.
CI fetches full history for this check. Add the feature commit first, then update its
matrix reference in a documentation commit; never insert a guessed future SHA.
