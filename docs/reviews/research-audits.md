# Independent review: research audits

Base: `52ba98b`; task plan: `docs/plans/research-audits.md`. Implementation was
integrated by root from the preserved concurrent snapshot, then repaired in the
isolated `codex/research-audits` branch. Independent reviewer: `source_audit`.

The review covered read-only inspection, scientific cache identity, interrupted
calls, model escalation, citation visibility/independent retrieval, held-out
feedback isolation, and preservation of the Table 5 initial assessment plus two
rebuttal cycles. It checked CONTRIBUTING.md and the task plan separately from the
scientific requirements. No blocking findings remain after the following fixes:

- Ordinary Markdown percentages no longer comment out subsequent citations.
- LaTeX comments respect odd/even preceding backslash parity, so hidden citations
  cannot validate an uncited manuscript.
- Inspection cache identity includes scientific state/configuration/source paths,
  but excludes persistence bookkeeping. Saving and reloading an interrupted run
  preserves prior inspected lines and failed-call evidence.
- Frontier audit escalation retains the operator's scientific task override.

Each finding was reproduced by a failing regression before its fix. Root also
added regressions for same-ID changed metrics, changed protocol/task, added source
files and failed provider-call persistence. The inherited broad transport-key
stripping test was superseded by the precise content-preservation regressions in
`tests/test_review_persistence.py`; scientific dictionaries retain their data.

Validation after final fixes:

- Independent reviewer: 119 tests passed in 32.63 seconds across inspection,
  agents, review, fidelity, experiment history, engine and writing.
- Root: 106 affected tests passed in 32.95 seconds (includes ScholarPeer persistence).
- Scoped Ruff checks/format, mypy on five source modules and git diff check passed.

Tests establish execution, evidence and routing properties. They do not establish
model correctness, exhaustive repository inspection or research capability parity.
