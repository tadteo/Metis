# Metis interface redesign

Base: 5f0cdd3. User requires rebuilding GUI/TUI/CLI aesthetic and usability. Accepted
preference: retro laboratory combined with Greek character, charcoal and cream in dark
and light modes, generous breathing room, clear and simple. References: user moodboard,
https://omarchy.org/, https://herdr.dev/, https://hermes-agent.nousresearch.com/.

Observed problem: persistent TUI sidebar plus twelve horizontal tabs, a five-line run
summary and global run actions leave too little space at 80×24. Settings is one long
form. Web has repeated calls to action, eight tabs, ungrouped controls, and dark-only
hardcoded colours. CLI startup emits a long manual before the first useful command.

Boundary: presentation, navigation and separate theme preference only. Keep all run,
setup, provenance, pause/resume, model-budget, export and machine-readable CLI features.
Do not alter scientific workflows or pinned research settings. Respect Metis identity.
Reuse completed setup worktree, new codex/metis-interface branch. Concurrent remote
interface implementation remains isolated and must be reconciled if it reaches main.

Implementation: shared charcoal/cream tokens, persistent separate interface preference;
full-width TUI view selector and command palette, contextual run controls, sectional
settings, short home and full guide; web research journal with meaningful spacing,
compact navigation, sectional settings and command menu; concise CLI welcome/grouped
help/human terminal status with unmodified JSON pipelines and NO_COLOR support.

Acceptance: every prior operation remains reachable; 80×24 terminal and narrow browser
remain usable; theme selection survives restart and never mutates run config; keyboard
focus and actions are discoverable; edited settings persist across sections; no action
is triggered by navigation/theme change; no hidden invalid field traps in setup; literal
research text remains inert. Shared colours have readable contrast in both themes.

Validation: behavioral Python/Node tests for navigation/theme/settings/CLI, visual QA
at desktop and narrow sizes in both themes, full repository checks and synthetic demo.
Independent review in a separate checkout, resolve findings, commit, update evidence
matrix with actual commit, merge only after tests/review. Preserve failed checks below.

Integration base advanced to 36fecfe after the reviewed managed SSH task reached main.
Preserved both sides of conflicts in CLI dispatch, bootstrap metadata, web handlers,
sidebar entry points, JS handlers, TUI button dispatch and browser test helpers.
SSH remains available through Connections and the TUI navigation selector.
Initial TUI check: 8 failures from queued navigation events/old sidebar assumptions;
fixed event guards and synchronization, then 19 passed. Initial mypy found a missing
Screen type parameter; corrected. Preview startup retries corrected a Path argument,
shell insertion syntax and required loopback bind permission; no research ran.
New theme/navigation/HTTP checks: 29 passed. Node checks before integration: 16 passed.

Independent review found and verified fixes for outgoing-pane focus reactivation and
execution shortcuts active while run controls were hidden. Regression tests cover both.
Usage/remote documentation now matches the selector, command palette and section flows.
Browser visual QA: desktop 1280×720 charcoal/cream, 390×844 settings, retained unsaved
fields, command menu, and a synthetic research overview. TUI screenshots inspected in
both colour modes plus Settings; 80×24 headless navigation tests pass. No live research
or remote authentication was initiated for this redesign.

Checks before final freeze: 101 affected tests passed; 30 Node tests passed; mypy passed;
26 TUI/appearance checks passed after review fixes; ruff and formatting passed after
correcting test fixture path lint and HTTP-test formatting. Wheel test first rejected
two wheels (old product-name build in dist); clean temporary build passed. Synthetic
demo completed with previous_best_retained_meta_refinement_not_superior.

First full run: 838 passed, 3 skipped, 2 blocked scientific rejection scenarios. Source
was edited during that run to apply review fixes; runtime_manifest hashes Python files,
so source drift is the likely explanation. Both scenarios subsequently passed on
unchanged main (23.44s) and frozen task source (22.26s). Full frozen rerun follows.

Final frozen suite: **842 passed, 3 skipped in 261.23s**. The installed wheel release
check passed separately (1 test); the optional upstream writer integrations remain
skipped by their normal environment gates. Node: 30 passed. Mypy: 67 files clean.
Ruff lint/format, specification validation and public scanner/self-test passed.
Semantic text/status palette contrast over bg/panel/raised has a minimum 5.96:1
in charcoal and 4.55:1 in cream. Integration inventory found main and all unrelated
checkouts clean; only this task and its completed review copy had changes.
