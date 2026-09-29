# Reconcile reviewed writer reliability changes

Integration base: `b1531d0`. Frozen upstream: `aeb24aa`; do not follow a moving branch.
This work preserves later concurrent, independently reviewed fidelity improvements while
retaining the AI-native catalog, writer material prompts, held-out projection and generic
accounting boundaries.

Port material changes and regressions from:

- `39a9385142b14418a4c920acd7a2bbca5c5447f5`: unresolved request journals per stage,
  stage-owned call identity, dependency invalidation and resumed failure preservation.
- `d7b006b425bb19797c3fedbfcee0b9807cd7ef44` and
  `5a1283909322902ec487a4ce73382de3f1fdcc8c`: process-group/container shutdown before
  accounting, torn-tail evidence preservation and durable idempotent reservation intent.
- `fa8f15ecd7c624dc45898276cb2644c74d413893`: expected plotting hashes from the pinned
  archive and exact materialized snapshot verification.

Scope: PaperOrchestra adapter, worker, setup, writer accounting adapter and writer tests/docs.
Keep Store accounting generic; coordinate any minimum idempotent-reservation API before
editing Store. Preserve public `resolve_writer_config`, shared `run_process`, versioned
material instructions, `memory.optimization_state`, frozen behavior and child ledger replay.

Compare exact frozen trees; port focused changes rather than overwriting current modules.
Run baseline and upstream regression suites, strict type/lint checks and relevant security
checks. Ask the coordinator for independent review before commits. Record accepted findings,
exact tests and remaining live-runtime limits in a review record. These checks establish
software behavior, not scientific writing quality or ScientistTwo capability parity.

## Implemented reconciliation and validation

The worker/setup deltas were applied from the exact frozen tree. The parent lifecycle was
transplanted selectively: versioned writer material guidance, the catalog fingerprint,
`optimization_state`, public writer configuration and shared process helper are retained.
`WriterAccounting` now reports child facts through `SubordinateCall` and the generic
`Store.settle` transaction; no writer-specific Store branch was introduced. Its durable
intent depends on the coordinator's independently reviewed generic idempotent-reservation API.
Existing crash-marker regression remains, alongside the upstream overrun and held-out tests.

- Ordinary development environment: 126 passed, one opt-in upstream smoke skipped across
  writer recovery/supervision/accounting, plotting, original writing, material prompts,
  generic accounting, Store/security, architecture and behavior/provenance tests.
- Actual writer source was verified clean at the adapter’s pinned revision
  `ca1b3fa01c2970fc7cda32d16245db38d57b3f56`.
- The existing pinned SDK environment passed all ten recovery and upstream-import/outline
  smoke tests. Their transport fixtures prevent live model calls. PyMuPDF emitted only
  upstream SWIG deprecation warnings. No paid call or full manuscript evaluation occurred.
- Ruff, strict mypy on all four changed/new writer modules, whitespace checks and the
  public-file content scan passed. The independent coordinator approved the reconciled delta before commits.

Generic Store prerequisite: coordinator commit `51ba993`, independently reviewed here and cherry-picked as `f4aef25`. The temporary Store test copy was restored before this cherry-pick; writer commits contain no Store implementation changes.

Final combined check after the reviewed Store prerequisite and coherent commit assembly: 128 passed, one optional upstream skip; Ruff and strict mypy passed. The actual-source SDK suite separately passed all ten tests as recorded above.
