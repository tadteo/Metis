# Pinned retrieval propagation review

Base: `f63e123`. Implementation branch: `codex/ai-retrieval-injection`.
Independent reviewer: integration coordinator, separate from this implementation.

Final Spec audit found that the Engine's pinned retrieval adapter was bypassed by
ScholarPeer's default runner. The repair passes the actual instance and checks its
identity at direct review entry as well as the Engine's existing continuation gate.
A custom runner factory must forward the Engine-declared adapter. Native writer
retrieval retains its separately documented upstream boundary.

The reviewer approved the source and all four adverse/live-protocol fixtures: the
actual adapter reaches review requests, a changed or omitted adapter fails before
calls, cutoff restoration covers success and failure, and scoped coverage preserves
prior historical searches without counting them as part of the current review.
No remaining actionable blocker was reported in this scope.

Validation: two integration fixtures reproduced the original missing-query failure
before implementation; the final retrieval/behavior/agents/review/persistence/
literature suites passed **81 tests** in 11.09 seconds. Ruff and strict mypy on the
three source modules passed, and whitespace checks passed. No external model or
retrieval call occurred. Root owns post-merge full-suite/release checks.
