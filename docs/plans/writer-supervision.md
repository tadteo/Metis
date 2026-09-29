# Writer supervision and journal recovery

Branch: `codex/writer-supervision`, isolated from `codex/official-writer`. This task depends on the parent writer/accounting foundation and changes only supervision/journal recovery, focused regressions, and review evidence.

The published writer remains official PaperOrchestra. These changes are operational safeguards: a completed client is not proof that the paid worker stopped, and interrupted journal writes must not silently lose or duplicate billing.

1. Reconcile the named Docker container independently of the client process and do not release reservations until the worker is confirmed stopped.
2. Stop and verify the whole owned local process group, including children that ignore SIGTERM or survive leader exit. Preserve uncertainty instead of automatically relaunching work.
3. Recover only a malformed final journal record, after confirmed worker exit. Preserve the torn bytes as an artifact, retain preceding durable reservation/completion records, and fail closed for interior corruption.
4. Add real-process regression tests and Docker mocks; confirm unaffected accounting tests, lint, and types.
5. Obtain independent parent review before committing a focused delta onto the committed foundation. Record findings and validation in docs/reviews/writer-supervision.md.

Do not edit the parent's worktree or the separate worker stage-recovery task.

Validation: final focused supervision/accounting suite has 20 passing tests; Ruff and mypy pass. Root independently reviewed the core delta and ran the original 19 tests successfully. See docs/reviews/writer-supervision.md. The final commit will be rebased onto the parent accounting foundation so it does not duplicate unrelated changes.

Final implementation is based on committed foundation `357d4a3` and also integrates the separately reviewed WriterAccounting parent receipt protocol. Final combined root review approved the delta with no blockers; 70 affected tests pass. No parent worktree was modified, and no unreviewed foundational code was duplicated into the task history.
