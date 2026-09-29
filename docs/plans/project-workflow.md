# Project workflow and architectural gates

Status: reviewed; baseline `6936a17`.

## Plan

1. Record the honest import boundary and the required development sequence.
2. Give future agents explicit pointers to architecture, source specification, fidelity evidence,
   decisions, tests and persisted run state.
3. Enforce critical live role dispatch through behavioral CI tests: iterative coding,
   official PaperOrchestra, published ScholarPeer context and independent critics.
4. Test this focused change; have another agent review the diff before committing.
5. Commit and merge the reviewed branch. Retain the review record and actual validation results.

## Acceptance

No new implementation history is attributed to the imported prototype. The handoff is usable
without chat history. Architectural tests fail if live specialist stages are bypassed. All
implementation agents use different worktrees; changes to a shared file are integrated explicitly.

## Baseline observations

The import was made while two pre-existing chats were developing in the original checkout.
It deliberately includes their unfinished work. Test failures and stale documentation in that
commit are preserved honestly; later commits repair them. The import is not a successful release.

## Results

14 architecture checks passed; Ruff and public-content scan passed. Independent review: `docs/reviews/project-workflow.md`.
