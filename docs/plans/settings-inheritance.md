# Model settings page and inheritance

Base: `4e6be44`. User requests a dedicated settings page with global defaults and
workspace/project overrides, including local and SSH workspaces. Credentials stay
on the execution host. Existing runs retain recorded configuration.

Reuse the clean managed checkout on codex/settings-inheritance. Add a shared,
validated model-settings layer (global > workspace > canonical project path),
optimistic revisions, explicit reset-to-inherited controls and a full-page browser
editor. Preserve existing saved workspace choices as legacy overrides. Scope is
model providers/routing and Laya, not project commands, filesystem paths or runtime
permissions. Full launch/run configurations still take precedence.

Global defaults live in a private per-user settings store. Connected managed SSH
controllers receive only model configuration snapshots over their authenticated
loopback tunnel. Disconnected workspaces sync on reconnect; failures are visible,
never reported as synced. Remote global settings are read-only copies managed from
the originating local console. No credentials, commands or project data are synced.

Validate cross-workspace inheritance, project isolation, reset, migration, stale
saves, remote snapshot propagation/failure, no automatic research/model calls,
CLI/TUI resolution and browser scope/save/navigation races. Inspect desktop/narrow
light/dark, keyboard focus, saved/unsaved/error states. Complete repository checks,
independent review, commit, fidelity evidence and merge. Preserve failed attempts.


## Implementation and validation

Model defaults now use private global storage plus workspace/project rows. Legacy
full-config saves change only explicitly edited model sections; all writers use
hierarchy-aware revisions. The browser has a real Settings page, inherited group
controls, retained drafts, JSON apply/save separation and run-specific overrides.
CLI supports scoped operations; inherited TUI defaults resolve for each new run.
SSH synchronization is authenticated, bounded, per-tunnel serialized and reports
pending failure without passing keys or running a new SSH connection.

Independent reviewer `/root/review_settings_inheritance` identified unrelated-save
pinning/project leakage, stale-parent legacy saves, CLI-to-TUI provenance and shared
editor request/state races. All were fixed with regressions and re-reviewed.
Additional validation-wait and SQLite error guards were fixed in the final review.
Final independent approval: no remaining blocking findings; 74 browser tests passed.

Attempts retained: a read initially named nonexistent remote_transport.py and was
corrected to remote.py. The initial browser test expected the old modal's readiness
message and was updated for the dedicated page. Two new HTTP tests initially used
the wrong helper keyword/tuple arity; corrected to the existing boundary helper.
Ruff found import ordering and a synthetic-token lint annotation; mypy required an
explicit integer conversion for the opaque revision. All were corrected.

Focused checks progressed through 93, 98 and 87 passing test sets; inheritance/CLI/
TUI checks passed 18 tests. A preliminary full suite passed 922 tests, 3 skipped.
The final suite passed 923 tests, 3 skipped and blocked one end-to-end test because
source changed during its run. This is the expected provenance safeguard, not a
research result. Source was then frozen and the single failed test rerun; result
recorded below. 74 final browser tests pass. Static lint/format (140 files), mypy
(74 source files), specification validation (47 agents/28 stages), secret scanner
and scanner self-test pass. Three authenticated scope/sync transport tests pass.

Visual evidence: disposable local state, zero research runs, desktop 1280×900 and
narrow 390×844, light/dark screenshots under docs/evidence/settings-inheritance-*.
Verified global Flash save, workspace Laya override, project override and reset,
server restart persistence, unsaved scope draft restoration, and editable new-run
model controls after selecting a project. Keyboard focus stays visible. An initial
pointer action during browser resizing hit the other checkbox; inspected state and
completed the journey with keyboard actions at fixed viewports. No credentials were
entered and no provider/Laya/research call was made. TUI layout is unchanged; its
new default-resolution behavior is tested. SSH transport uses a real authenticated
loopback controller fixture, not a live remote deployment.

The provenance-gated end-to-end rerun passed in 38.02 seconds after source freeze.
Installed wheel test passed (1 test, 39.51 seconds); offline demonstration completed
with the previous best retained after nonsuperior meta refinement. Temporary UI
server and browser tab were closed; viewport reset. No user settings store was
modified during validation.

Feature commit: `e0d8138`. Main advanced independently to `2bac842` (automatic
source selection); integrated into this branch without conflicts. Other dirty
review checkouts were inventoried and left untouched. Combined setup/browser and
inheritance checks run before integration.

Combined integration validation: 163 Python tests passed (54.22 seconds) across
model inheritance, legacy settings, profile routing, setup/source policy, web and
fidelity matrix; 76 browser tests passed. The independent reviewer approved the
combined source-selection flow with no new findings and reran all 76 browser tests.
