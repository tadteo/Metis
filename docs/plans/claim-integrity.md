# Claim integrity implementation plan

Branch: `codex/claim-integrity`; baseline: `6936a17`.

The published requirement is that manuscript claims agree with executed research evidence. The exact ledger, numeric units, rounding rules, and artifact receipts below are local engineering enforcement, not recovered upstream implementation.

1. Bind every numerical claim to an exact displayed numeric span. Derive precision from its literal representation and require explicit operator-owned metric units before unit conversion. Reject mismatched text/value, unsupported conversions, duplicate experiment links, or excessive rounding tolerances.
2. Replace statistical file-existence checks with an execution-owned capture protocol: declared input experiment fingerprints, deletion of declared stale outputs immediately before protected evaluation, completed analysis execution, captured output SHA-256, and a strict structured statistical result. Bind reported statistics and comparators to that output.
3. Add positive and adversarial regression tests, including unchanged/preexisting artifacts, output tampering, stale inputs, failed analyses, unit conversion and misleading rounding.
4. Document extraction schema and execution integration. Own the necessary project configuration and execution receipt capture; coordinate engine metadata integration with the separate engine task.
5. Run focused tests, lint, type checks and the existing suite. Obtain independent parent review before making implementation commits.

Do not remove failed analysis records or negative statistical results. Validation failures remain explicit issues; they do not synthesize successful evidence.

## Validation and review

Independent parent review requested LaTeX percentage/bound parsing and an explicit relative-change aggregation. Both were added with regression tests. The final affected suite has 88 passing tests (37 claim-integrity tests and 51 execution tests). Affected-source Ruff and mypy pass. The first full-suite run exposed existing engine/writer test mismatches, a TUI lifecycle race, and sandbox-denied web sockets; those are assigned to integration rather than hidden or relabeled as claim-test success.

Independent review: root approved the revised implementation and independently ran all 37 claim tests successfully. Scientific semantics and study-design validity remain the responsibility of the separate integrity panels. Engine metadata wiring is a dependency of the separately reviewed research-loop branch; this task supplies the documented schema and execution boundary.
