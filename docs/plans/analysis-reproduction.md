# Executed analysis reproduction integration

Status: implementation and integration tests complete; independently reviewed and approved for commit.
Starting point: reviewed `codex/experiment-history` (`ffc550e`). Dependency: reviewed `codex/claim-integrity` (`a02d767`).

## Plan

1. Create `codex/analysis-reproduction` in this free worktree and merge the reviewed claim branch with an explicit merge commit; retain both branches' real history.
2. Bind formal experiment specifications to operator-declared metric units, analysis outputs, and fingerprinted completed input results.
3. Reproduce analyses with the original declared outputs and original input descriptors, excluding subsequently completed experiments. Compare normalized statistical analysis output as well as benchmark metrics; differing p-values must fail verification even if metrics match.
4. Add integration regressions exercising actual protected local evaluators, metadata propagation, changed inputs, differing statistics, and successful equivalent receipts.
5. Run history, fidelity, engine, claim-integrity, and execution suites; lint/type-check changed source. Ask root for independent review before committing the new integration implementation.

## Evidence and constraints

ScientistTwo requires code re-execution to support reported numbers ([paper §4.2](https://arxiv.org/html/2609.19644v1#S4.SS2)). Registered structured analysis artifacts and fingerprints are local engineering mechanisms for that requirement. Reproducibility alone does not establish that the statistical procedure is scientifically appropriate; independent claim and method audits remain necessary.

This task owns the engine integration, focused tests, and review/plan documentation. It does not edit the original checkout or official writer integration. Failures and uncertain outcomes remain in persisted experiment history.

## Implementation and validation

Dependency merge: `5e04a2b` preserves the reviewed claim-integrity branch's commit history. Formal execution now records configured units, declared statistical outputs, and fingerprinted completed input observations. Independent reproduction reuses those original declarations and observations, and compares normalized statistical results as well as benchmark metrics. Output formatting or a new execution receipt does not count as a scientific discrepancy; a changed or missing statistic does.

`tests/test_analysis_reproduction.py` runs actual local protected evaluators against explicitly synthetic observations. Five regression cases cover propagated metadata, exclusion of failed inputs without deleting them, unchanged input selection despite later experiments or config changes, changed and missing statistical outputs with matching benchmark metrics, and equivalent JSON with different formatting and receipt hashes.

Validation on the integrated branch:

- `PYTHONPATH=src pytest -q tests/test_analysis_reproduction.py tests/test_experiment_history.py tests/test_fidelity.py tests/test_engine.py tests/test_claim_integrity.py tests/test_execution.py`: **135 passed** in 35.05 seconds.
- `ruff check --no-cache src/autoresearch/engine.py tests/test_analysis_reproduction.py`: passed.
- `mypy src/autoresearch/engine.py --follow-imports=silent`: passed.

The separately persisted second review of the claim-integrity dependency is in `docs/reviews/claim-integrity.md`. Root independently reviewed the engine diff and all five integration cases, found no blocking issues, and independently ran `tests/test_analysis_reproduction.py`: **5 passed** in 1.72 seconds. Root approved the focused integration commit after that review. No scientific model claims or publication-quality experimental results are inferred from these synthetic software tests.
