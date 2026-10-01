# Available models and automatic routing

Base cdb5291. Approved prototype: codex/model-setup-prototype, fb10e82.
Replace only model settings with compact inventory, Configure/Add model, preserving
Home, Appearance and non-model settings. Keep Laya/System 1 independent. Provider
credentials remain host-local and outside configuration. Project settings offer all
models or selected IDs; exclusions must constrain routing. New inquiries inherit
models without a model-setup step. Advanced explicit configurations stay supported.

Implement a typed inventory with compatible-provider configurations and separate
project allowlist, shared settings inheritance and optimistic revisions, local access
status (never claim provider verification), automatic new-run route compilation and
immutable run snapshots. Routine roles choose lowest configured token estimate;
critical work retains configured primary when eligible, otherwise an eligible model.
Legacy explicit configurations remain unchanged unless inventory is enabled. Native
writer/command adapter limitations must be enforced or surfaced, never silently bypass
an allowlist. No live provider calls for tests or setup. Existing runs stay pinned.

Validation: focused routing/settings/credential/web/browser tests, full required CI
checks, synthetic GUI desktop/narrow both themes and keyboard/dialog journeys;
independent review before commits/merge. Update routing guide, settings guide and
fidelity evidence after feature commit. Preserve failed checks and external limits.

## Implementation and review evidence

Implemented compact inventory and independent System 1 dialogs, project permissions,
partial optimistic saves, host-local status, and deterministic new-run route snapshots.
Home/Appearance remain in place. Advanced explicit edits opt out of inventory routing;
legacy workspace/global configurations remain explicit until inventory is saved.

Independent reviewer: `/root/review_prototype`. Review found and corrected normal
inquiry navigation, inherited project inventory pinning, duplicate entries on key-save
retry, hidden password retention, legacy global activation, and ignored advanced
primary edits. Re-review approved with no blocking findings, contingent on checks.

Synthetic GUI inspected at desktop and 390px narrow widths, cream and charcoal:
model Configure/save, independent Laya dialog, project Only selected models/save,
Return to inquiry retaining question/folder, and Project → Review navigation. Keys
were synthetic session fixtures; state was temporary; no provider calls were made.
Evidence is under docs/evidence/model-inventory. UI status is not account entitlement
verification, live model discovery, quality validation or measured savings.

Preserved failed checks: initial focused 89 passed, browser 86 passed. Review fixes
expanded browser coverage to 91 passing. First full run: 978 passed, 3 skipped, four
failures: two immutable behavior guards fired because source changed during execution;
one inheritance regression was fixed; one old test assumed fresh settings lacked the
new inventory and now asserts original-value preservation. Later focused writer fixture
failed after primary-inventory validation was added; fixture now explicitly selects
its fake endpoint, so it reaches the native-writer identity guard being tested. Ruff
cache permission errors were resolved with --no-cache; import and mypy errors fixed.
An automatic approval rejection flagged potential global-store test mutation; verified
the autouse temp-settings isolation and added explicit temporary METIS_SETTINGS_HOME
to the new legacy-global test before proceeding. No user settings were changed.

Integration inventory: main advanced from cdb5291 to cab845a for the separately reviewed
research-process feature. Other active checkouts inspected. Uncommitted historical
review edits in temple-review and temple-refinement-review were left untouched; all
other non-task checkouts clean. Prototype branch/server retained separately.

Pre-integration validation: 987 passed, 3 skipped, one CLI entry-mode fixture failed
because fresh live inventory now requires an accessible model before snapshotting.
Added a synthetic credential resolver to that entry-mode test (no paid calls); all
14 affected routing/entry regressions pass. Browser suite: 91 passed. Ruff lint and
format pass; mypy: 82 source files; specs: 48 agents / 29 stages valid. Wheel installed
artifact test: 1 passed. Scanner/self-test pass. Isolated offline demo completed with
empty error. Integrated-tree full checks follow after merging latest main into branch.

Integrated cab845a validation: 997 passed, 3 expected skips in 318s; browser suites
98 passed; mypy 83 source files; Ruff lint and formatting (153 files) pass. Installed
wheel check passes; public scanner and its self-test pass. Synthetic integrated UI
loads with no browser errors. Conflict resolution retained both process and inventory
assets, correct script order and both CSS sections. Separate reviewer approved these
integration resolutions. No experimental or scientific success is inferred.

Final ledger updated with actual feature commit 97e3654 and regenerated packaged/docs
reports. Independent documentation review approved; 17 fidelity checks and specification
validation pass. Final wheel rebuilt after ledger regeneration: installed-artifact check
passes and both inventory Python/JS assets are present. Final public scan passes.
