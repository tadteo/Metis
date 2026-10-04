Implement summarize(text: str) -> dict in summary.py to summarize experiment CSV.
Keep the implementation self-contained in summary.py; additional check files are allowed.
Use only Python's standard library. Preserve the interface; do not alter smoke.py.

The header must be exactly method,seed,status,score in that order, after stripping
whitespace from each field. Use real CSV parsing, including quoted commas/newlines.
Ignore empty physical lines. Strip surrounding whitespace from every value. Each
record has exactly four fields and a nonempty method. Seed is an ASCII digit string
representing a nonnegative integer (leading zeroes allowed). Status is success or
failed. A success score must parse as a finite float; a failed score must be blank.
Reject invalid headers, records and duplicate normalized (method, integer seed)
identities with ValueError; never silently discard them. Missing header is invalid.
Header-only input returns {}.

Return a dictionary keyed by method. Each value has exactly attempted, succeeded,
failed, mean, stdev. Counts include every valid attempt; statistics use successful
scores only. Mean is null/None if there are no successes; sample standard deviation
(n-1 denominator) is null/None with fewer than two successes. Retain methods with
only failed attempts. Numerical answers must match Python statistics.mean/stdev to
1e-12 relative/absolute tolerance on moderate finite values. Do not replace missing
or failed scores with zero. Inputs are small in-memory data.

Read the existing code, implement the task, and execute meaningful checks before
finishing. Return a runnable check command as final argv. Independent acceptance
checks run later on exported source. This is a software task on synthetic data;
do not claim research improvements from passing it.
