# Claim evidence contract

ScientistTwo's published integrity checks require agreement between claims, measurements, citations and implementation. The exact ledger and receipt formats here are local enforcement policies, not recovered upstream formats. They establish numerical and artifact consistency; independent coverage, citation-entailment and method audits still assess completeness and scientific meaning. A statistically valid computation does not by itself establish that its assumptions or study design are appropriate.

## Numerical claims

The extractor supplies the exact `text`, a unique `numeric_span`, `value`, `metric`, `aggregation`, and `experiment_ids`. `value` is the literal displayed number: `51.0` for `51.0%`, rather than `0.51`. The complete span includes its displayed unit and comparator. LaTeX `51.0\%` and mathematical `\leq`, `\geq`, `\le`, and `\ge` bounds are supported directly, without altering the manuscript span. When there is exactly one numeric expression the verifier can infer the span; multiple expressions require an explicit span. Each substantive number needs its own ledger entry.

Completed measurements can be linked individually, averaged, or differenced in the specified order. `relative_change` uses exactly two experiment IDs in new-result, baseline order and computes `(new - baseline) / abs(baseline)`; a zero baseline is undefined and fails validation. A negative change denotes a reduction, rather than silently reversing the sign for a lower-is-better metric. Relative changes may use `%`; absolute changes in fractional or percent metrics use `percentage points`, avoiding an ambiguous absolute-difference-to-percent conversion. Duplicate experiment IDs and mixed units fail validation. Rounding is bounded by half the last displayed decimal unit, including scientific notation. An optional `rounding_tolerance` can tighten this bound but cannot enlarge it.

`project.metric_units` is operator-owned configuration. Allowed units are `scalar`, `fraction`, `percent`, `percentage_points`, `seconds`, and `milliseconds`. Explicit percentage and time suffixes require matching units or supported conversions. For example, a measured fraction `0.5101` supports `51.0%`, and `0.025` seconds supports `25.0 ms`. An unadorned literal retains the measurement's registered unit. Differences of fractions can be displayed as percentage points. Unsupported or unregistered conversions remain issues for repair instead of guessed conversions.

## Executed statistical evidence

The operator registers output paths in `project.analysis_artifacts`, for example `["analysis.json"]`, and supplies a protected evaluator that computes those outputs. Registration cannot target `metrics.json` or protected source files. The engine supplies completed experiment descriptors via `analysis_input(result)`; each contains `id`, `metrics`, seed/method/plan provenance when available, and a SHA-256 fingerprint covering the exact experiment record. Evaluators can use those registered fields to identify paired seeds and comparison groups. Reproduction reuses the original analysis input descriptors, output declarations, and metric units. It must reproduce every valid captured statistical result as well as the benchmark metrics. Changed or missing statistics fail verification and remain in experiment history; JSON formatting differences or new receipt identifiers do not change an otherwise identical analysis.

The evaluator reads these descriptors from the JSON file named by `AUTORESEARCH_ANALYSIS_INPUTS`. This file is in the protected evaluator snapshot and mounted read-only in Docker. Local and Slurm retain their existing trusted-host execution assumptions. A declared output is removed immediately before the protected evaluator runs, so neither a preexisting file nor a file emitted only by the proposed training command can be accepted as the evaluator's analysis output.

Each output has this JSON schema:

```json
{
  "schema_version": 1,
  "method": "two-sided exact sign test",
  "metric": "score",
  "statistic": "p_value",
  "value": 0.5,
  "input_experiment_ids": ["exp-a", "exp-b"],
  "input_fingerprints": {
    "exp-a": "exact fingerprint copied from the registered input descriptor",
    "exp-b": "exact fingerprint copied from the registered input descriptor"
  }
}
```

The identifiers above are illustrative. Supported statistic names are `p_value`, `test_statistic`, `confidence_lower`, `confidence_upper`, and `effect_size`. Only declared outputs of completed formal executions get receipts. Receipts retain the parsed result, execution ID, and exact output hash in `ExperimentResult.provenance.statistical_analyses`. Invalid or missing outputs retain diagnostic receipts; they cannot support claims. Other measurements and failed experiments remain in the research record.

A statistical claim sets `analysis_experiment_id` to that execution, `analysis_artifact` to its registered output, and `experiment_ids` to the analysis inputs. Its `metric` and `statistic` must match the executed result. The verifier requires unchanged artifact bytes, unchanged completed input records, and an exact match to the captured receipt. It checks the displayed number or bound: an executed p-value of `0.5` cannot support `p < 0.001`. Existing arbitrary files, stale inputs, failed runs, and changed output files cannot establish support. Hash verification detects mutation; it does not rely on filesystem permissions as an immutability guarantee.

## Method validation and significance

The generic contract proves that displayed statistical values match unchanged executed evidence. Supported registered methods additionally receive independent arithmetic validation. See [registered statistical method validation](statistical-analysis.md) for the paired sign-flip plan and execution contract. Explicit significance/nonsignificance conclusions require that validation; unsupported methods retain executed-value evidence with `method_validation.validated: false` rather than receiving an implied methodology approval.

## Validation

Run `PYTHONPATH=src pytest tests/test_claim_integrity.py tests/test_execution.py tests/test_analysis_reproduction.py`. The focused tests include real local protected-evaluator execution, exact number/value binding, units and rounding, aggregate provenance, negative statistical results, stale artifacts, post-execution tampering and changed inputs. The repository's ordinary CI runs these tests with the rest of the suite.
