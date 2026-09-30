# Specialist dispatch extraction

Base: `2cf77f0`. Status: complete; integrated in `5a2380f`.

## Request and boundary

Extract AgentRunner's specialist dispatch so coding-backend experiments and research
changes are localized. Preserve scientific decisions, ordering, external command
precedence, model-call accounting/cache/routing, inspection escalation, writer evidence,
review checkpoints/coverage and demo behavior. No new backend, prompt or workflow changes.
Reuse the clean attached worktree after the completed diagnostics task.

## Design

A specialist module owns typed advice, inspection, coding, writing and review preparation.
Its small dispatch interface either returns a specialist result or prepares context for
the existing ordinary panel. It receives explicit store/config/catalog/literature and a
typed callback for accounted calls; it does not depend on AgentRunner or its private
methods. AgentRunner keeps common output validation, panel consensus and call accounting.
Split specialist implementations into focused methods, preserving dispatch order.

## Acceptance and sequence

1. Baseline specialist/agent regression suites; preserve attempted-command evidence.
2. Extract implementation and update test patch locations at their actual dependency seam.
3. Add behavior tests for specialist precedence, context isolation and callbacks as needed.
4. Focused tests, full pytest, lint/format/types/specs, browser tests, private synthetic demo,
   package build/installed wheel, public scan and fidelity checks.
5. Independent review and resolution; feature commit then evidence mappings using its real
   SHA. Merge only after validation; record post-merge checks and preserve other checkouts.

No paid calls. Existing pinned runs retain recorded-runtime requirements; a source
refactor is not permission to migrate their behavior identity. Software tests do not
establish autonomous research quality.

## Completed implementation and validation

SpecialistDispatcher owns focused advice, inspection, coding, writing and review
methods. AgentRunner keeps common validation, consensus and the accounted callback.
The run method is 171 lines (previously 391). No backend, prompt or policy was added.

Independent review approved the implementation and corrected fixture locations.
Fresh full pytest: 946 passed, 3 skipped. Browser suite: 85 passed. Installed wheel:
1 passed. Synthetic demo completed; lint/format/types/specs/public scanner and scanner
self-test passed. See the review record for the initial fixture failures and resolution.

Post-merge verification: 103 specialist, accounting, retrieval, review-persistence and
fidelity tests passed. Merge was conflict-free; unrelated checkouts remain untouched.
