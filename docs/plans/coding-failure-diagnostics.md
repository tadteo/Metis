# Coding failure diagnostics

Base: `1403bf9`. Status: complete; integrated in `d153ab0`.

The user narrowed the task to reproduction and diagnostics for encountered failures.
Reproduce an exhausted coding session with a real failed command. Improve its final
error so operators can locate the preserved session and understand the latest failure
without digging through checkpoints. Preserve redaction, bounded output, complete
private history and existing resumption behavior. No dispatch refactor, broad journey,
paid calls, scientific policy or UI redesign is included.

Acceptance: regression fails before the fix; actionable bounded/redacted diagnostics;
focused coding/engine tests and repository checks; independent review; real commit
references in fidelity evidence; merge after validation. Record attempts and limits.

## Implementation evidence

The concrete failure is generic budget exhaustion hiding an already preserved failed
command. New errors include counts, a relative checkpoint locator and the latest
recorded failure with redacted/bounded output. All three coding budgets use this path;
no commands are rerun and no scientific or budget semantics change. The affected
operator journey is reading a blocked-run error and locating its private checkpoint.
No layout or navigation changes; text behavior is covered by executable regressions.
See `docs/reviews/coding-failure-diagnostics.md` for attempts and independent review.

Validation complete: 936 Python tests passed (3 skipped), 85 browser tests passed,
installed wheel passed, synthetic demo completed; lint/format/types/specs/public scan
and scanner self-test passed. Independent review approved with no blocking findings.

Post-merge coding and fidelity checks: 38 passed. Integration was conflict-free;
unrelated checkout changes remain untouched.
