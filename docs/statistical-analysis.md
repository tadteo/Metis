# Registered statistical method validation

This integrates the concurrent paired sign-flip implementation with the existing [claim evidence contract](claim-integrity.md). Statistical-method validation is a local integrity safeguard, not a statistical procedure prescribed by ScientistTwo. The protected evaluator, registered outputs and fingerprinted input observations remain the only execution-evidence path.

## Registration and execution

For the supported paired sign-flip test, create `statistical_plan.json` in the source before the formal experiment starts:

```json
{
  "schema_version": 1,
  "test": "paired_sign_flip",
  "metric": "score",
  "pairs": [
    {"left": "candidate-seed-0", "right": "control-seed-0"},
    {"left": "candidate-seed-1", "right": "control-seed-1"}
  ],
  "alternative": "two-sided",
  "alpha": 0.05,
  "family_size": 1,
  "correction": "bonferroni",
  "assumptions": "Explain independent paired units, exchangeable difference signs under the null, and inference scope."
}
```

The two pairs above illustrate the schema; six positive nonzero differences are needed for a two-sided p-value below 0.05 with family size one. Supported alternatives are `two-sided`, `greater`, and `less`. Register the evaluator's output path in `project.analysis_artifacts` and configure its protected script as described in the claim contract.

The executor captures and hashes the plan bytes before starting generated code. The protected evaluator reads that copy through `AUTORESEARCH_STATISTICAL_PLAN`; it reads host-owned observations through `AUTORESEARCH_ANALYSIS_INPUTS`. A plan first created during training cannot establish registration. Changing the later workspace copy cannot change the archived registration. Independent reproduction requires the original plan bytes and the original input fingerprints.

The evaluator writes the existing generic output schema, for example:

```json
{
  "schema_version": 1,
  "method": "paired_sign_flip",
  "metric": "score",
  "statistic": "p_value",
  "value": 0.5,
  "input_experiment_ids": ["candidate-seed-0", "control-seed-0"],
  "input_fingerprints": {
    "candidate-seed-0": "copy from the registered input descriptor",
    "control-seed-0": "copy from the registered input descriptor"
  }
}
```

The identifiers and value above are illustrative; an actual output must include every registered pair. Use `statistic: effect_size` for a separately declared artifact containing the mean paired difference. The output paths are configurable; the old concurrent fixed `statistical_analysis.json` format is adapted to this receipt schema rather than retained as a second loose-file attestation path. Stale outputs are deleted before the protected evaluator runs.

## Arithmetic and provenance checks

The plan requires 2–20 distinct pairs of completed inputs. Each observation appears once; each pair shares an integer seed, and different pairs use different seeds. All observations must share an immutable specification SHA-256, consistent nonempty dataset provenance, and registered metric units. Each treatment group's source SHA-256 must be constant across its seeds. Exact fingerprints bind every input to the original completed experiment, including its provenance.

The host independently enumerates all `2**n` sign assignments over measured `left - right` differences. Two-sided testing counts absolute sums at least as large as the observed absolute sum; one-sided testing uses the corresponding signed tail. Numerical ties use tolerance `max(1, abs(observed_sum)) * 1e-12`, inherited from the concurrent implementation. The adjusted p-value is `min(1, raw_p * family_size)`. The reported effect must equal the mean measured difference. Nonfinite derived arithmetic is rejected. Invalid registered-method outputs fail the execution, retain measured metrics and a diagnostic receipt, and cannot support claims.

The receipt contains `method_validation` with the independently recomputed p-value, mean difference, alpha and plan hash. Registration timing, inputs, artifact bytes and validation are rechecked when verifying claims. The ordinary numerical `numeric_span`, literal displayed value, registered-unit and rounding rules remain authoritative.

## Conclusions and limits

Set a statistical claim's `statistical_conclusion` to `significant`, `not_significant`, or `estimate` (the default). Significance requires adjusted p strictly below registered alpha; nonsignificance requires p at least alpha. Explicit manuscript wording cannot be overridden by an `estimate` annotation. Statistical prose without a printed number may assert a conclusion only when a supported method validates it. Printed planned statistics use `p = NUMBER`, `p < NUMBER` (also `<=`, `>`, `>=`, Unicode and LaTeX comparisons), `mean difference = NUMBER`, or `effect = NUMBER`. Other quantities need separate exact claim spans. Each equality uses displayed precision; inequalities require the actual relation.

Other methods can still provide fingerprinted executed-value evidence through the generic contract. Their receipts say `validated: false`; they cannot establish significance conclusions until a method-specific validator is implemented and reviewed. Executed-value consistency must not be described as independent validation of a statistical method.

Arithmetic and provenance checks do not establish that the plan preceded inspection of existing results, that the complete comparison family was declared, or that paired observations are independent and sign-exchangeable. The receipt explicitly leaves those facts unverified. Fixed-dataset seed variation alone does not establish population-level generalization. Comparing recorded dataset provenance does not certify undeclared dataset properties or substitute for the separate file-manifest checks. Independent scientific panels must review those assumptions and selection effects.

Run `PYTHONPATH=src pytest -q tests/test_planned_statistics.py tests/test_claim_integrity.py tests/test_analysis_reproduction.py tests/test_execution.py`. Fixtures use synthetic observations and actual local protected-evaluator subprocesses; they establish software behavior, not scientific capability.
