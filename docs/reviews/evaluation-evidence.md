# Public-data evaluation integration review

Independent reviewer: workflow_audit. The concurrent evaluation implementation was inspected
before integration and tested with real protected local workloads. Three reproduced findings
were fixed with initially failing regressions: partial workspace setup was not registered;
suite-level exceptions could produce successful CLI reports; diabetes applied loader scaling
before splitting. Attempts now precede setup, suite errors are retained separately from
resumable run status, and raw diabetes features receive training-only preprocessing.

The reviewer also identified that the two-reference variant had configuration without engine
wiring. The integrated loop now consumes both query count and minimum independent coverage;
tests exercise the real gate with two sources. Report labels now state the improvement
rate's all-attempted-idea denominator, include pending ablations, and identify command metrics
as completed-observation rates.

Evidence: 20 evaluation tests passed, including all three red-to-green regressions and actual
baseline execution; Ruff/mypy passed. The reviewer rechecked the three repairs and found only
a test CLI flag typo, corrected to --state-dir before the passing run. A fresh 12-attempt public
baseline report replaces the old scaled-input report; the superseded record is retained and
marked unsuitable as protocol-valid evidence. Autonomous model capability remains unmeasured.
