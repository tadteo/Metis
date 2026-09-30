Implement a faithful subset reproduction of the reference method. Inspect the
research brief, supplied resources and papers. Reuse existing work or build what
is missing. You own the reproducible experiment command; any imported command is
context, not an automatic override. Match data, splits, seeds and task metrics.
Run pilots/checks and repair failures through the coding tools. Never fabricate
measurements, source values, data or labels.

For agent entry without a sealed research_protocol, finish with structured.protocol:
metrics (name to max/min), sota (original published FULL benchmark numbers),
reference_sources (metric name to {evidence_id, location, excerpt}), specification
(the sourced task rules, subset/full datasets and splits, restrictions, coverage),
evaluator_argv (argument array for measurement), protected_paths (measurement/data
assets), dataset_manifest (sha256:path to digest), metric_units, analysis_artifacts,
measurement_checks (argument arrays for independently recomputable measurement
checks or known examples), measurement_artifacts (paths to predictions/logs consumed
by measurement). Include complete measurement source in exported edits. The scorer
may adapt the benchmark's own test suite; no user-written scoring script is required.
Published full values are not subset reproduction expectations. If no defensible
reference values or data can be obtained, abort honestly and retain the diagnostics.
The pipeline independently inspects this proposal and executes its measurement
checks before sealing a protocol. Check commands must demonstrate meaningful
measurement behavior, not print a claimed score. Hardcoded metrics, changed labels,
leaked splits or dropped benchmarks are invalid. Once sealed, candidate agents
cannot change the measurement assets or task rules. Actual baseline measurement
and independent scientific assessment still follow coding completion.

If measurement is instrumented within method code, specify measurement_mode:
"instrumented", measurement_paths containing the source that computes scores, and
an empty evaluator_argv. Fixed data/labels still belong in protected_paths. All
underlying measurement_artifacts must be regenerated in each formal run. The
pipeline checks the original measurement source, independently inspects each
candidate and repeats its pristine experiment before eligibility. Prefer a separate
scorer where clean separation is scientifically possible. Registered statistical
analysis currently requires that separate protected scorer; do not invent support.
