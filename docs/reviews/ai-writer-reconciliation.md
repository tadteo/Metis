# Writer reconciliation independent review

Integration base: `b1531d0`; frozen upstream tree: `aeb24aa`.
Independent reviewer: coordinating root agent, before implementation commits.
The exact upstream fixes are `39a9385142b14418a4c920acd7a2bbca5c5447f5`
(stage recovery), `d7b006b425bb19797c3fedbfcee0b9807cd7ef44` (supervision),
`5a1283909322902ec487a4ce73382de3f1fdcc8c` (reservation intent foundation), and
`fa8f15ecd7c624dc45898276cb2644c74d413893` (plotting provenance).

## Review outcome

The reviewer approved the final reconciliation with no blocking findings:

- Stage context survives nested executors. Swallowed adapter/budget failures remain
  unresolved request evidence; a poisoned checkpoint invalidates its dependent stages.
- Container and complete process-group termination precede journal repair and accounting.
  Unknown liveness retains reservations. Torn tails are preserved, not silently discarded.
- Durable intent uses the generic idempotent reservation API. Child usage facts and the
  aggregate charge settle atomically through the generic Store ledger; there is no
  writer-specific Store implementation or doubled attempt denominator.
- Expected plotting hashes derive from the pinned archive, not a mutable installation
  receipt. Source/tracked-style verification and exact copied-snapshot verification remain.
- Versioned material prompts, catalog fingerprints, held-out projection, public configuration
  resolver and shared runtime helper were preserved. Existing root crash regressions were
  retained alongside later upstream tests.

The pre-versioned `settle_worker_accounting` utility remains solely for explicitly
reconciled historical reservations and their recovery regressions. The active writer path
uses only `WriterAccounting` and refuses automatic legacy receipt migration.

Generic Store prerequisite `51ba993` received a separate independent review by this writer
implementer: 25 accounting/security tests passed, and 24 concurrent reservation requests
created one durable aggregate hold. It is cherry-picked here as `f4aef25`, separate from
writer commits.

## Validation

Ordinary writer/accounting/security/architecture/behavior suite: 126 passed, one optional
upstream smoke skipped before the two Store prerequisite regressions were added. All four
writer implementation modules pass strict mypy; modified source/tests pass Ruff. The
public-content scan and whitespace checks pass.

The pre-existing SDK environment and clean official source at
`ca1b3fa01c2970fc7cda32d16245db38d57b3f56` passed all ten actual-source recovery and
outline/import tests. Fixtures disable or replace network transports; no paid request or
full manuscript quality evaluation occurred. PyMuPDF emitted only SWIG deprecation warnings.
Local process-group supervision retains the documented trusted-host assumption; a deliberately
detached process requires external containment. Docker remains the isolated default.

Final combined check after the reviewed Store prerequisite and coherent commit assembly: 128 passed, one optional upstream skip; Ruff and strict mypy passed. The actual-source SDK suite separately passed all ten tests as recorded above.
