# Statistical/evaluation reconciliation review

Implementation base: `b1531d060aa9c2fe0d954b521bf7ab8fd3efe4ad`.
Frozen upstream reviewed source: `aeb24aac515f8451f669c44ca00937a370c645db`.
Scope, original review references, architectural adaptations and validation results are recorded in [the task plan](../plans/ai-statistics-reconcile.md).

Independent reviewer: the separate scientific reconciliation agent (`audit_science`). The reviewer checked Standards and Spec, including execution receipts, statistical correctness, archived negative attempts and reference parsing.

## Findings and resolution

1. **Unit-dependent exact-test and effect tolerances.** The inherited absolute floor changed p-values under positive rescaling and admitted wrong tiny effects. Replaced tail comparisons with exact integer arithmetic over recorded float differences; removed the absolute effect floor, rejected mean underflow and documented the precision boundary.
2. **Additional labeled tiny effects.** Correct primary p-values could coexist with an incorrect tiny signed mean because a secondary text check added an absolute tolerance. Replaced it with Decimal displayed-rounding bounds and added honest/opposite-sign/zero fixtures.
3. **Rejected-refinement denominator.** A hypothesis created after its experiment was omitted from improvement-rate attempts. Added hypothesis-to-retained-experiment linkage through archived proposal/decision memory, while excluding unexecuted seeds.

## Disposition and evidence

After re-reading the corrections, the reviewer independently passed 13 targeted counterexamples. The full planned-statistics, evaluation and claim-integrity selection produced 106 passes and one known root-owned CLI failure; an inexact exclusion name left that test enabled. Root implemented the CLI status fix in its separate integration scope. The reviewer reported no remaining actionable Standards or Spec blocker and approved these changes before commit.

The author additionally passed the same 106 tests with the exact CLI case deselected, seven-module mypy, Ruff, formatting, diff check and public-artifact scan. Earlier execution/program/integrity and catalog/provenance checks are preserved in the plan. Scientific engine wiring, prompt role registration and CLI behavior still require validation in the combined Git tree before main integration. No live paid evaluation was performed.
