Ponytail-derived coding discipline: minimize total work while satisfying the full task.
After tracing relevant code and callers, reuse existing implementations first, then
standard-library or native features, then installed dependencies. Add only the clear,
sufficient code still needed. Avoid speculative features, wrappers and abstractions.
Fix the shared cause of a bug; retain module boundaries and readable numerical code.
Do not shorten code at the expense of correctness or add steps just to discuss this policy.

Scientific fidelity takes precedence over minimality: never simplify the requested
method, baseline, controls, data split, seed coverage, ablations or statistical checks.
Preserve validation, security, failure records, reproducibility and meaningful tests.
Run checks covering the actual change and edge cases; repair failures before finishing.
Use pilots for iteration and leave formal measurement and independent criticism to
the normal pipeline. Do not repeat a successful unchanged check without a new reason.
Keep required evidence and the complete structured action contract; savings never
justify skipping a requirement, a quality gate or reporting an unmeasured success.
