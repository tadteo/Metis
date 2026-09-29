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
At that checkpoint, combined checks remained pending until concurrent scientific repairs were reconciled.
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
  actual immutability assertion. Final focused run: 63 passed; scoped mypy over 4 modules passed.

- Generalized typed advisory contracts preserve noul, choice and ordered scores, with
  externally declared criteria and strict dependent output schemas. Author checks: 69 tests,
  independent checks: 48 tests and scoped mypy over 3 modules/Ruff passed. The independent prompt integration
  reviewer caught unchanged draft/revise versions after adding statistical material;
  raised both to 1.2.0. Scientific/catalog integration: 106 tests passed.
- Catalog cherry-pick initially conflicted where the new attribution type met moved
  typed-answer classes. An over-batched shell command attempted tests before resolution
  and produced seven syntax collection errors. Retained both implementations, reran
  the 106 integration tests successfully, then completed the cherry-pick.
- Rich console reconciliation independently reviewed and committed; combined TUI/CLI/
  typed provenance: 44 tests passed after adapting CLI to selected_run and config_path.
- Installed-wheel demo passed twice (24.36s and 24.48s); second check explicitly verifies
  import location and all packaged program sources after independent review identified
  possible editable-source fallback. Final rebuilt-wheel check still follows the merge.

## Final history reconciliation

Main `87bf703` finished concurrent fidelity repairs after the initial architecture
snapshot. Its capabilities were ported and independently reviewed before merging
its ancestry. Source conflicts retain the reviewed composed implementation; docs/CI
retain the newer schema2 fidelity ledger, generated reports, real writer job and
evaluation-extra installation. Main's review-budget reinterpretation is explicitly
resolved in paper-spec A04 and the reconciliation plan. Replaced historical writer-
specific accounting tests remain covered by the generic ledger and migration suite.

The merge initially duplicated the preflight block despite reporting no conflict;
source diff review caught it and retained one implementation. The new fidelity
validator found the renamed configurable-rebuttal test reference; updated the
ledger to the actual test node before generating reports. An unused fixture
variable from the earlier security regression was removed after Ruff caught it.

Final independent maintainer review found three additional integration issues:
cache hits reported configured rather than actual/repair model provenance; binary
web responses incorrectly appended a charset; the web server did not pause and
join research workers on exit. It also found that ScholarPeer bypassed an injected
retrieval adapter. The fixes and adverse regressions are recorded below.

## Final independent review and release verification

Standards review (`runtime_cleanup`) found cached output provenance used configured
model/provider rather than its producing response, particularly after schema repair
or frontier escalation. `9ea5164` stores actual call provenance in a typed cache
envelope; legacy cache entries explicitly mark unknown actual identity. Independent
boundary checks: 147 passed; cache/agent: 74 tests plus 7 cache/UI tests passed.

Spec review (`audit_science`) compared normalized ASTs of every upstream scientific
branch with extracted handlers and found only the documented architecture/A04
changes. An independent clean snapshot ran 192 scientific/provenance tests. The
reviewer found custom retrieval was bypassed by ScholarPeer: the fix forwards and
verifies the injected adapter, restores its cutoff and scopes per-review history
without discarding earlier searches. 81 focused tests passed. The reviewer also
corrected the fidelity ledger to describe held-out review as configured, not universal.

External-maintainer review (`audit_platform`) found binary MIME and web shutdown
gaps. `b2851a5`/`b4bccff` preserve exact PDF content and pause/join active workers
on every server exit; 48 focused tests passed. The merged web/security selection: 42
tests passed. A cherry-picked fixture assertion initially lacked its earlier baseline
variable; Ruff caught it, and the declaration and preservation assertion were retained.

First full reconciled suite: 728 passed, 2 failed, 3 skipped in 189.43s. Both failures
were legacy review test doubles rejecting the new checkpoint keyword; confirmed
with a two-test reproduction. Fixtures now execute that callback and assert its
artifact, retaining their review-before-panel and coverage gates. The last retrieval
fix and these fixtures are included in the final run recorded below.

Release checks so far: Ruff, formatting 111 files, strict mypy over 60 source modules,
public scan, scanner self-test, offline frozen lock check and 9 Node browser tests
passed. Schema 2 fidelity validation: 17 tests passed after ancestry merge. Generated
reports retain actual current test nodes and both branch histories.

## Final accepted tree and integration evidence

The final full suite passed **734 tests, zero failures, three optional skips in
187.10s**. The opt-in installed-wheel test passed separately in 38.28s, including
verified installed import location, packaged program compilation and the complete
synthetic workflow. All 10 actual pinned upstream writer/recovery tests passed in 4.65s;
only existing PyMuPDF/SWIG deprecation warnings were emitted. Mypy passed 60 source
modules. Ruff passed, all 112 files were formatted, all 9 Node browser tests passed,
and the final committed fidelity matrix passed 17 tests in 1.05s. Public scan, scanner
self-test, offline lock check and diff whitespace checks passed.

The final Spec reviewer independently approved the checkpoint fixture and conditional
held-out documentation changes, rerunning 31 focused tests and verifying canonical,
packaged and generated fidelity equality. The final contributor-documentation review
verified 46 agents, 28 stages and all local links; it corrected reviewer scales to
ICLR 1–10 / NeurIPS 1–6 and clarified that `specification_dir` customizes agent artifacts,
not the installed workflow graph. These are documentation corrections only.

The standalone CLI demo completed with 34 experiment records, two preserved rejected
refinements, 140 scripted calls, zero API cost and zero outstanding reservations. Its
outcome retained the previous measured incumbent after unsuccessful meta-refinement.
A post-demo accounting probe initially supplied a string where Store requires Path;
correcting that diagnostic argument returned the confirmed accounting totals. No
runtime source change was required.

Source, test and packaged asset content is pinned by commit `59d2708` and the public
hash in [ai-native-validation.json](../evidence/ai-native-validation.json). Later edits
only finalize documentation/evidence. The original main checkout was clean at
`87bf703`; its history is already an ancestor through the explicit reconciliation
merge `56888ab`. The reviewed task is ready for the development workflow's local
merge without squashing its component commits or rewriting the inherited snapshot.

Hosted CI and live research-quality evaluation remain unexecuted. No paid model
call, original 107-task replication, live Docker/TeX success or scientific capability
parity is inferred from these results. The earlier independent fidelity evidence
and validation records are retained rather than overwritten.
