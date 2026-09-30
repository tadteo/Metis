# Settings inheritance independent review

Base: `4e6be44`. Reviewer: `/root/review_settings_inheritance`.
Scope: storage, model resolution, migration, credentials, SSH propagation, browser
scope/navigation races, CLI/TUI behavior and documentation. No reviewer code edits.

## Findings resolved

- Unrelated legacy saves pinned inherited values and could promote a project's
  provider into workspace defaults. Preserve section provenance and compare edits.
- Concurrent parent changes were invisible to legacy revisions. Use a hierarchy
  fingerprint as an opaque safe integer and serialize global/local transactions.
- CLI passed resolved defaults as explicit TUI config. Preserve actual launch
  provenance and reload inherited defaults for new runs.
- Pending Settings initialization and scope fetches could overwrite new inquiries.
  Use editor/request generations; restore enabled controls and retain JSON drafts.
- Pending validation could act on a replacement editor. Guard after the wait.
- SQLite store errors were not covered by pending synchronization status. Catch
  sqlite3.Error and retain the last acknowledgement.

Other improvements reviewed: remove duplicate source listener, preserve later
non-model edits while resolving a project, await inheritance before validation,
refresh unedited scopes, serialize SSH snapshots and validate response objects.

Final reviewer outcome: approved, no remaining blocking findings. Independent
checks: 18 focused Python tests in the main review, 74 final browser tests, plus a
direct SQLite-failure check. No provider calls. Coordinator owns full-suite,
installed-artifact and visual acceptance evidence in
[the task plan](../plans/settings-inheritance.md). This review establishes no
scientific quality, model availability or cost-saving result.
