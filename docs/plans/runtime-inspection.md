# Runtime inspection surfaces integration

Base: `8ad2d49` on `codex/evaluation-evidence`.
Status: independently reviewed; ready for focused commits, with final matrix integration owned by root.

## Ownership and provenance

This focused branch reuses a clean isolated checkout after the independently reviewed
ScholarPeer task. The source is the frozen final concurrent-work snapshot identified by
`/private/tmp/scientisttwo-concurrent-final.json` and stash
`dd5ea451520072415e742484fccbb401f00014a6`. The pre-existing code was developed by another
chat after the honest prototype import; this task integrates and verifies it without inventing
historical commits. The original TUI plan remains alongside this integration plan.

Own: TUI, web/static assets, CLI runtime inspection and fidelity commands, artifact content
read API and immutability checks, focused tests and fidelity module/JSON scaffolding.
Exclude: scientific source inspection, agents, engine, prompts, writing and review modules.
Preserve the integrated evaluation command, accounting reservations and Store usage logic.
Root will reconcile final component commit/evidence mappings in the fidelity data.

## Plan and acceptance

1. Inspect preserved UI/CLI changes and import only the owned files; merge Store/CLI deltas
   surgically so newer budget/evaluation behavior remains intact.
2. Run focused TUI, web, artifact security, CLI and fidelity tests plus browser script checks.
   Add regression tests for integration issues found during review.
3. Confirm raw private artifacts remain authenticated and immutable, and terminal startup
   supports run creation and selection using persisted Store state.
4. Obtain independent root review and record it, then create a focused Conventional Commit.

A feature is complete only after executable tests, independent review, documentation and a
reviewable commit; root handles integration to main separately.

## Implementation and validation

Imported 16 files from the preserved tar only after checking every SHA-256 against its frozen
manifest. Store changes were restricted to artifact write/read methods; idempotent writer
reservations and subordinate usage accounting are unchanged. CLI keeps the public evaluation
command while exposing fidelity and the current TUI constructor.

The combined TUI, CLI, web and Store suites passed 62 tests before independent review;
the additional review-requested missing-artifact regression and Store/web rerun passed
41 focused tests. Six Node browser-form tests pass and
now run in ordinary CI. Additional regressions cover bounded immutable artifact reads, hash
corruption rejection, path confinement, exact PDF downloads and evaluation/fidelity CLI
coexistence. Integration testing exposed a TUI shutdown race: an interval queried removed
widgets after Textual stopped the app. A deterministic regression failed with `NoMatches`
before adding a stopped-app refresh guard, then passed. Binary downloads also now use their
actual content type without a text charset. The public TUI command opened in a PTY and exited
with Ctrl+Q, status 0; its private store contains zero runs.

The fidelity module and JSON are preserved scaffolding. Its path-resolution test is intentionally
still failing on audit/test documentation being integrated by separate focused branches
(`test_inspection`, `test_integrity`, `test_laya`, primary-source/statistical docs). Root owns the
final evidence/commit matrix; do not weaken this gate or fabricate evidence to pass it.

## Independent review follow-up

Reviewer `workflow_audit` identified one blocker in the imported artifact immutability guard:
a deleted registered file could have its historical path reused for new bytes. The regression
failed before the fix. Registration now looks up the historical path before checking file
existence and refuses reuse if registered bytes disappeared. The original missing path and
artifact metadata remain unchanged, preserving evidence of the loss. Independent re-review
approved the fix after three targeted artifact tests passed. Full matrix validation still
awaits the documented branch dependencies.
