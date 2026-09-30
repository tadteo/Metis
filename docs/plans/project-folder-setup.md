# Project folder creation and selection

Base: `a367ffb`. User requests automatic project folder creation/filling or a folder
picker, and questions exposing internal experiment setup as a user choice.

Use an isolated codex/project-folder-setup branch. Add authenticated server-side
folder browsing (so SSH selects remote folders) and unique private project folder
creation. Fill the draft path after creation/selection; create automatically during
Check setup when blank. Preserve existing folders and never fabricate code, metrics,
or protocol. Remove the redundant Experiment setup mode; retain inspection and
manual overrides through progressive disclosure. A fresh empty folder remains
unready until actual research inputs exist. No scientific stage changes.

Validate authenticated routes, collisions, invalid paths, no runs/model calls,
stale browser responses, cancellation, inheritance refresh, existing configuration,
and keyboard/browser rendering in both themes and viewport widths. Obtain independent
review, commit implementation, update fidelity evidence, merge and check integration.
Record actual checks, failures and limitations below.

## Implementation and evidence

Browser paths are selected by an authenticated host-side folder browser, rather than
an upload input (which cannot give a usable SSH server path). New directories are
unique, private and empty under the private Store's projects directory. Project model
inheritance is refreshed after selection. In-flight creation cannot overwrite newer
path edits; navigation/cancellation invalidate stale browsing responses. A blank path
is created on Check setup. Scientific readiness remains mandatory.

72 authenticated HTTP tests and 83 browser tests passed. Ruff lint/format (141 files),
mypy (75 modules), specification validation, public-file scan and diff checks passed.
Independent review findings and their resolution are in the companion review record.

Visual/keyboard QA: disposable loopback controller with private synthetic state;
1280×900 and 390×844, light/dark. Exercised explicit creation, automatic creation,
folder navigation and selection, cancellation focus, invalid location, long names,
advanced experiment-field access, and an empty folder's disabled Create action.
No model or research workload ran. Screenshots: docs/evidence/folder-*.png. TUI/CLI
layout is unchanged. The browser uses the controller host; no live SSH deployment
was contacted. Full-suite result is recorded below when complete.

Attempts preserved: initial branch creation needed filesystem escalation; a temporary
edit script emitted a harmless Python escape warning; Chrome was unavailable and QA
used the in-app browser. Early pointer actions did not open setup; keyboard activation
worked and the rest of the journey used keyboard controls. The first narrow picker
render exposed nowrap overflow; fixed and verified before acceptance. One browser
locator incorrectly treated summary as a button; corrected to its DOM summary element.
A fidelity script lookup used the wrong name before discovering update_fidelity_report.py.

The full offline suite passed: **930 passed, 3 skipped in 344.34 seconds**.
The synthetic demo completed with the previous best retained after nonsuperior meta
refinement; it is engineering evidence only. All task source remained unchanged after
the narrow CSS repair for the remainder of validation. Independent re-review approved
the final implementation and independently passed all 83 browser tests.
