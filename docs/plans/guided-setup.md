# Guided startup and settings

Base: 0425e2a. Source: user request for a finished, intuitive GUI/TUI/CLI with startup guidance, initial configuration, missing-prerequisite help and settings management.

Boundary: shared private defaults for future runs; welcome and setup entry points in all three interfaces; editable common settings and full JSON escape hatch; actionable local readiness. Scientific stages, existing run configuration and execution authorization remain unchanged. No provider calls, automatic installs or workload execution during setup.

Acceptance: first launch explains the lifecycle and demo/live choice; returning users can reopen help/settings; partial setup can be saved and resumed across interfaces; explicit config files override defaults; invalid edits cannot overwrite settings; concurrent edits cannot silently clobber settings; keys remain environment references. Show source/data/evaluator, model, execution, budget, privacy and writer requirements. Only explicit run actions execute research.

Checks: persistence/restart/conflict/invalid input tests, CLI interactive and noninteractive paths, Textual pilot first-run/settings/new-run paths, HTTP auth and immutable existing-run checks, browser form and stale validation tests, visual browser and terminal inspection. Run repository lint/types/full pytest/Node/spec/fidelity/scan/demo and package validation. Independent review against base, resolve findings, commit then update fidelity evidence and merge.

Execution record: initial branch creation in the managed worktree required filesystem escalation after a sandbox lock error. No scientific attempts are performed by this interface task.


Validation history: the initial sandboxed focused run could not bind loopback HTTP
sockets or write tool caches. After running with the required filesystem/socket access,
56 tests passed; one new fixture incorrectly assigned an invalid Pydantic value outside
its expected-error assertion and was corrected. Three original TUI tests needed to
navigate the new welcome screen; explicit config launches now retain the New run path.
Initial lint found import ordering; resolved by formatter. Initial Node suite passed
all 9 tests, then all 12 with new settings round-trip/save/conflict coverage. Types passed.
Browser inspection at 1280×720 confirmed the welcome cards, settings dialog, sticky
actions, field help and actionable credential/source/evaluator/writer checks.

Public-file scan initially flagged a deliberately invalid token-shaped test string; replaced it with an invalid variable-name fixture. No real credentials were involved.

Independent review found and reproduced the advanced-map-removal bug; corrected with
schema normalization and regression tests. Follow-up review reported no actionable
findings. See docs/reviews/guided-setup.md for validation and measurement boundaries.

Status: implemented, independently reviewed and validated; feature commit 63b0364.
Fidelity evidence uses that actual commit. Final wheel and matrix checks pass. Integration
uses a merge commit into main; concurrent remote-interface branches remain separate.
