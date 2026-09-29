# Independent review: claim-integrity evidence binding

Reviewed commit: `a02d767` against baseline `6936a17`.
Reviewer: `source_audit` agent, independently of the implementation agent (`workflow_audit`) and the root review.
Sources: the user's fidelity requirements, `docs/paper-spec.md`, `docs/plans/claim-integrity.md`, `CONTRIBUTING.md`, and the diff `git diff 6936a17...a02d767`.

## Standards

No blocking findings. External claim values and analysis outputs are validated through explicit models; captured statistics remain behind the executor boundary; malformed, missing, tampered and stale evidence produces recorded issues. The implementation introduces no new dependencies. New configuration and evidence semantics are documented, and focused tests exercise observed behavior rather than mirroring helpers.

## Specification

No blocking findings within the reviewed branch scope. Numerical manuscript literals are checked against registered units and executed observations, including LaTeX percentages and explicit relative changes. Statistical claims require an executed, fingerprinted artifact associated with unchanged input results; arbitrary preexisting files cannot establish significance. The independent source review specifically checked that measured negative statistical outcomes cannot be relabeled significant by changing the claim ledger.

Integration dependency: engine specifications must supply declared analysis outputs and the original fingerprinted inputs, and independent reproduction must compare statistical outputs in addition to headline benchmark metrics. A changed p-value must fail reproduction even when those metrics match. This dependency is addressed and tested separately on `codex/analysis-reproduction`.

## Validation

The reviewer independently ran `PYTHONPATH=src pytest -q -p no:cacheprovider tests/test_claim_integrity.py`: **37 passed** in 2.85 seconds. `git diff 6936a17...a02d767 --check` passed. Root separately reviewed the same claim implementation and independently ran its focused suite.

These checks establish evidence-binding software behavior. They do not establish that an executed statistical procedure is scientifically appropriate; the independent claim, coverage and method panels retain that responsibility.
