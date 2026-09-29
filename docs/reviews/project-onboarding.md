# Project onboarding independent review

Base: 38910cb. Reviewer: independent agent `onboarding_review`, with a separate
checkout at `.codex/worktrees/onboarding-review/AutoResearch`; reviewed the task
snapshot and successive deltas without editing the implementation checkout.

Finding: P1 — the AI prompt included current project and execution settings that
were absent from the preview. A private specification sentinel reproduced the
mismatch. Fixed by returning/rendering exact outbound system/prompt and destination,
and applying structured redaction before serialization. A regression binds preview
to the saved outbound request and verifies secret-key redaction.

The reviewer approved the fix and selected-source evidence revalidation. Advisory
suggestions cannot change providers, budgets, executable permissions or local-execution
authorization. Draft files remain inert. Atomic request claiming prevents duplicate
provider calls; failed/uncertain attempts and available usage remain private. Review
clarified the documented launcher detection limit: recognized direct/nested launchers
are detected, not arbitrary Python code that might submit work.

Independent checks: 111 Python tests across onboarding, setup, HTTP boundaries,
agent specifications and behavior; 34 browser tests. Initial socket tests required
filesystem/network sandbox escalation before passing. One initial reviewer command
named a nonexistent test module and exited before execution; the corrected command
passed. Final presentation/HTTP deltas receive a follow-up review recorded below.

Parent validation: 859 Python tests passed, 3 optional integration/package checks
skipped in the ordinary run (260.65 seconds). The installed wheel check passed
separately. All 68 source files pass mypy; Ruff lint/format and specification checks
pass. Public-artifact scanner and scanner self-test pass. Browser suite now has
35 passing tests. A local synthetic provider exercised inspect → exact request preview
→ propose → reload/recover → selected application → readiness review; no paid model
or cluster job ran. New-project manual path, keyboard access, both themes, and narrow
390px / desktop 1280px layouts were inspected. Narrow dialog geometry stays within
viewport without horizontal overflow; browser viewport override was reset afterward.

Limit: this is implemented web onboarding and bounded advisory generation, not measured
AI setup quality, a working target-specific GPU adapter, or scientific capability.
