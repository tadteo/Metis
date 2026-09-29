# AI-native platform integration review

Review base: `9cd457d` (pre-change audit and acceptance plan), on top of the
explicit inherited-working-tree snapshot `92a9ace`. Scope: the full AI specification,
workflow, runtime and inspection refactor. The original checkout is not used as a
scratch worktree; concurrent research repairs remain separately owned.

## Independent review and fixes

The Standards reviewer (`audit_platform`) and Spec reviewer (`audit_science`) did
not author the coordinator's behavior, memory or UI integration. Their first pass
found substantive issues before these changes were committed:

- Immutable bundle inspection called a missing Store API. Added bounded descriptor-
  based artifact reads with size/hash receipts, symlink/special-file rejection, and
  corruption fixtures; authenticated downloads use the same boundary.
- The TUI refreshed a widget that had not been composed. Added its AI-system pane
  and preserved text rather than JSON-encoding it. The Textual startup test inspects
  the recorded graph/contracts without executing research.
- External command entrypoint changes and injected provider configuration changes
  escaped provenance checks. Pin executable/script hashes and stable configured
  identities; live custom extensions must supply an explicit behavior identity.
- Command writers were displayed as official upstream writers. Route inspection now
  reports the command adapter and leaves its actual model identity to its receipt.
- Relative custom specification paths could fail after changing directories. Run
  creation persists their absolute location; a cross-directory resume test covers it.
- Legacy adoption checked only top-level state. A separate legacy-journal audit rejects unreconciled subordinate work before migration.

A subsequent external-maintainer pass found two residual instruction strings: the
Laya advisory triage question and manuscript evidence-reporting guidance. Both now reside in the versioned specification layer with runtime provenance.

Component review/evidence lives in `ai-agent-specs.md`, `ai-runtime-tools.md`, the
workflow review and `generic-accounting.md`. Accounting review independently caught
and repaired a legacy replay mismatch between redacted events and raw worker facts;
new ledger replay remains strict and original historical events remain intact.

## Validation history

- Inherited baseline: 288 passed, 2 failed, 1 skipped. The two writer architecture
  fixtures returned an outdated string contract instead of manuscript/references.
  Fixtures now model the actual interface and retain their dispatch assertions.
- First integration run: 333 passed, 25 failed, 2 skipped. The missing artifact-read
  boundary caused the dominant failures; it was repaired before further validation.
- Next full run: 356 passed, 2 failed, 2 skipped. Both failing fixtures changed an
  executor after run creation, which the new drift guard correctly rejected.
  Injection now occurs before creation; the resumption scenarios are preserved.
- Focused repaired behavior/store/TUI/fidelity run: 37 passed.
- Strict mypy: all 55 source modules passed at this checkpoint. Ruff passed. The
  initial type check exposed CLI optional narrowing and the Textual quit override;
  both were repaired, without suppressing the checks.
- Node interface suite: seven tests passed before final integration additions.
- A read-only Ruff attempt could not write its cache in the managed worktree;
  it was repeated with proper worktree write permission. A diagnostic process-list
  command was unavailable in the sandbox; no implementation relied on it.

The core provenance re-review (`runtime_cleanup`, independent of its implementation)
found three additional counterexamples: nested retrieval overrides, class factory
identities and extensionless script entrypoints. These are fixed with regressions.
The reviewer independently reran 40 behavior/storage/literature tests and confirmed no
remaining blocking finding in that scope. Factory identity now handles classes and
bound methods; retrieval identity describes actual providers; command executables are
persisted as absolute paths and all absolute file arguments are hashed. Python module
entrypoints must be replaced by pinned script entrypoints.

The inherited format-only cleanup was mechanically checked by AST equivalence across
all six affected files and committed separately (`eb93da2`); it changes no behavior.
Final combined checks remain pending until concurrent scientific repairs are reconciled.
Offline tests and synthetic end-to-end runs demonstrate software behavior only.
No live model execution or scientific capability parity is claimed.

## Reconciliation checks and findings

- Coordinator reservation recovery API was independently reviewed by `audit_platform`:
  25 accounting/security tests passed; a separate 24-call concurrent reservation probe
  produced one charge and one hold. Committed as `51ba993`.
- Writer reconciliation independent source review approved stage-scoped failure
  receipts, process/container shutdown before billing, generic atomic settlement and
  pinned reference hashes. Agent checks: 126 passed, 1 optional skip in ordinary venv;
  ten tests passed against actual pinned upstream source and installed SDKs without
  network/model calls. See the writer reconciliation record for commits.
- First coordinator artifact/migration/setup reconciliation run: 57 passed, one failure.
  Imported missing-file test expected FileNotFoundError; the stronger descriptor reader
  deliberately exposes ExecutionError for unsafe/missing workspace paths. Updated only
  that expectation, retaining missing-byte/history assertions.
- Reciprocal scientific review found a unit-dependent tolerance in exact paired
  sign-flip statistics and an improvement denominator omitting rejected refinements.
  Both require repair and regressions before integration. A conditional ablation
  output schema also required correction so legitimate refinement is not rejected.

The later scientific integration on main is preserved with explicit capability ports
and an ancestry merge, never relabeled as newly authored architecture work. The peer
review budget interpretation is recorded in `docs/plans/ai-fidelity-reconciliation.md`.

- Coordinator artifact/migration review found that artifact creation bypassed the safe
  reader for existing paths and unknown writer schema versions could claim legacy
  settlement. Reused descriptor-based reads and required explicit supported versions.
  Added FIFO and unknown-schema regressions. A fixture initially counted two creation
  artifacts instead of three; changed it to compare original rows, preserving the
  actual immutability assertion. Final focused run: 63 passed; scoped mypy4 passed.

- Generalized typed advisory contracts preserve noul, choice and ordered scores, with
  externally declared criteria and strict dependent output schemas. Author69 tests,
  independent48 tests and scoped mypy3/Ruff passed. The independent prompt integration
  reviewer caught unchanged draft/revise versions after adding statistical material;
  raised both to1.2.0. Scientific/catalog integration106 tests passed.
- Catalog cherry-pick initially conflicted where the new attribution type met moved
  typed-answer classes. An over-batched shell command attempted tests before resolution
  and produced seven syntax collection errors. Retained both implementations, reran
  the106 integration tests successfully, then completed the cherry-pick.
- Rich console reconciliation independently reviewed and committed; combined TUI/CLI/
  typed provenance44 tests passed after adapting CLI to selected_run and config_path.
- Installed-wheel demo passed twice (24.36s and24.48s); second check explicitly verifies
  import location and all packaged program sources after independent review identified
  possible editable-source fallback. Final rebuilt-wheel check still follows the merge.
