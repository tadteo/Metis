# Ponytail pilot — 2026-10-01

**No live task completed, so neither cost savings nor preserved output quality was
established. Ponytail remains opt-in.** These are negative/inconclusive operational
results, not measurements that Ponytail lowers scientific quality.

The [public machine-readable report](results.json) preserves every attempted arm,
errors, elapsed time, reported tokens, uncertain reservations, prompt/task hashes and
unattempted slots. Complete private journals/specifications/checkpoints are archived
locally under the project's ignored `.autoresearch/ponytail-20261001/` directory;
the report records the archive hash. Nothing was deleted to improve the comparison.

| Battery | Planned / attempted | Result | Priced reported tokens | Unknown-usage reservations |
|---|---:|---|---:|---:|
| Flash coding loop | 6 / 6 | Every attempt ended in HTTP 503; one completed a list action first | $0.00434625 | $0.17553975 |
| Grok coding loop | 6 / 3 | Two structured-action failures, then transport timeout; remaining arms unattempted | $0.16885 | $0.149504 |
| Grok single-response probe | 2 / 1 | Baseline transport timeout; Ponytail unattempted | $0 | $0.08952 |

Total accounted estimate: **$0.58776**, comprising **$0.17319625** from reported
usage at configured prices and **$0.41456375** conservatively reserved for unknown
remote outcomes. None is an invoice; unknown reservations must not be reported as
observed generated tokens. Provider prices were the existing configured estimates.
Docker/local compute costs are not measured.

The task was a self-contained CSV experiment summarizer using standard Python.
The independent suite checks failed-only groups, all attempt counts, sample rather
than population standard deviation, quoting/whitespace, invalid headers/records,
normalized duplicate identities and numerical accuracy. No generated implementation
reached this suite. We therefore have zero live acceptance observations.

Both arms used the same model, fixed task, fresh workspace, no local response cache
or frontier fallback, and identical budgets within each battery. API requests
contained only the public synthetic task, empty state, instructions and defaults.
Generated execution was configured for Docker with networking disabled and no host
data mounts. Model endpoints used their existing credential references; credentials
were not logged or passed to generated code.

The first battery exposed a runner stopping bug: conservative nonzero token estimates
were mistaken for usable provider output. Independent review caught it; later
batteries stop on ProviderError and keep all prior failures. Before the second battery,
the task explicitly required self-contained summary.py and the acceptance receipt
was strengthened to require all seven groups to complete. The optional single-response
probe is a distinct protocol and cannot be pooled with coding-loop measurements.

Offline scorer tests accept a known correct implementation and reject population
standard deviation and early-exit implementations. They also exercise provider-outage
stopping and verify the optional bundle preserves the original coding protocol,
tool permissions, output validation and all other agents. These are software checks,
not a replacement for live model quality or a successful cost comparison.

Default adoption requires successful complete coding-loop comparisons with all
quality gates passing and lower aggregate cost. A single fixture would still not
establish broad non-inferiority or scientific performance. No default policy, model
routing or existing run configuration was changed after this failed adoption gate.
