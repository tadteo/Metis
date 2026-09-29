# Self-building temple

Base: `83ab407`. User requests replacing the Home pixel temple with a three-dimensional
Greek temple assembled from falling bricks, preferably ASCII or a similar graphic,
with mouse rotation in GUI and TUI. The supplied photograph informs the colonnade,
stepped foundation and pediment; attached markup identifies the existing Home mark.

Boundary: decorative Home presentation and its local controls only. Use one packaged
geometry/timing asset with browser and Textual renderers. Preserve the question-first
journey, research settings, scientific state and execution controls. Follow VIBE.md's
shared palette. No new dependency or external media/network asset.

Acceptance: blocks build upward from foundations through columns and roof; finished
architecture is readable from multiple angles. Drag and keyboard rotation, pause and
replay are discoverable. Stop animation after assembly and while hidden; browser
reduced-motion and terminal animation-disabled preferences show a completed temple.
Keep new-research actions visible at 80x24; detailed temple remains reachable by scroll.
Desktop/narrow browser and 80x24/120x40 terminal work in both themes. Animation is an
identity metaphor, never an indicator of measured research progress.

Validation: geometry/assembly and interaction regressions, browser and terminal visual
inspection with synthetic empty state, focused suites then relevant full CI checks.
Independent agent review against the base in a separate checkout, record findings and
resolutions; conventional feature commit, actual-commit fidelity update and merge.
Preserve failed checks and limitations in this plan. No paid research or live SSH.

User refinement during preview: remove the Greek caption and interaction instructions
from the art, slow the build, and drop individual stones straight down without swept
waves. Updated to deterministic shuffled releases within courses, a 23-second build
and constant vertical speed; no automatic rotation. GUI controls use accessible icons;
TUI bindings appear in the existing footer only when the temple has focus.

## Validation record

Initial checks found two integration mistakes: Textual's inherited action_toggle
signature conflicted with the local action, and the static JSON route passed bytes
into the server's JSON serializer. Renamed the scoped action and decoded geometry at
the route. Initial mypy also required narrowing widget ancestors before reading their
regions. The first focused run then had 71 passes and one incorrect test assumption:
front/back silhouettes of a symmetric temple are equal. The rotation regression now
compares front, oblique and side views. The subsequent four temple tests passed.

The browser runner import was unavailable in the generic Node REPL; visual checks used
the supported in-app browser. Pointer-based locator clicks sometimes failed in that
browser environment; keyboard activation and the actual pointer-drag API worked.
Desktop and 390px widths, both themes, arrow rotation, pointer rotation, icon pause /
resume and reset were inspected with an empty synthetic store. No horizontal overflow
at 390px. The user saw the original sweep during preview and requested the refinement
recorded above. The updated preview shows separate vertical stones with no captions.

Terminal Home and the focused temple were rendered at 80x24 and 120x40 in both themes.
The compact temple fits its scroll viewport and inquiry actions remain visible above
it on initial Home. Screenshot rendering uses macOS QuickLook; no private runs appear.
Independent review found foundation clipping at maximum terminal tilt; resolution and
final revalidation are recorded in the review document.

Ruff lint, mypy (71 source modules), 43 Node browser tests, specification validation
(47 agents, 28 stages), public-file scan and scanner self-test passed. The installed
wheel regression passed with the new scene, browser script and terminal renderer.
The synthetic offline demo completed with outcome
previous_best_retained_meta_refinement_not_superior and no execution error. These are
software checks, not scientific capability evidence.

The first full-suite run was intentionally interrupted after 129 passing tests when a
parallel format check found one HTTP-route formatting change. Formatting was applied
before restarting the suite to avoid changing runtime source hashes during tests.
No scientific attempt, result or failure was discarded. The release checks were run
with the existing locked development environment and loopback/subprocess permissions.

Pre-integration inventory: main is clean at the recorded base. Existing uncommitted
changes in inquiry-entry-refinement and onboarding-review remain untouched; the
separate simplify-setup worktree is also outside this task. The task and independent
review each use their own managed checkout.

The frozen full suite passed: 873 tests, 3 conditional skips in 283.87 seconds.
Independent review then identified two terminal presentation issues: clipping at
maximum tilt and an initial compact viewport that counted the widget border as visible
and could play before its art appeared. Framing now fits the completed geometry's
projected bounds with a cell margin; visibility uses clipped content regions. New
regressions cover both terminal sizes, pitch extremes, five yaw angles, and waiting
before scrolling the compact temple into view. The first framing edit missed a
formatted source literal and left scale undefined (7 failed, 4 passed); corrected
immediately, after which the 11 framing/inquiry checks passed. Final affected-suite
and independent revalidation follow below. The full scientific suite had already
finished before these presentation fixes; no source was edited during that run.

After both independent-review fixes, all 34 affected terminal/inquiry tests passed
in 58.44 seconds; the rebuilt installed wheel test passed in 40.48 seconds. Mypy,
Ruff and formatting checks pass. Main advanced concurrently to `d890295` with the
separately reviewed simplified model setup task. Integrate that work before the
final merge and rerun the affected browser checks; preserve both tasks' evidence.

Feature commit: `767fb78`. Integrated the current main (`d890295`) automatically in
`6e9bde1`, preserving the separately reviewed model-access setup, without conflicts.
The combined browser suite passed all 48 tests. Combined fidelity/temple/inquiry
checks passed 29 tests in 22.81 seconds, and the public-file scan passed. Updated the
canonical fidelity matrix and regenerated packaged JSON and reports with the actual
feature commit. The independent reviewer approved both terminal fixes after 70
Python tests, 43 pre-integration browser tests and actual browser interaction checks.

The final main merge encountered another independently reviewed concurrent task:
`6e707f1` / `badcda4` clarified inquiry entry after the previous inventory. Its HTML
conflict was resolved by retaining the question-led heading, multiline question field,
reassurance and Continue to setup action, alongside the new temple figure and script.
CSS, TUI and browser tests merged automatically. Existing inquiry/temple tests were
adapted from Input.value to TextArea.text/load_text to match the new field; no input
behavior was reverted. Independent review and all affected checks were requested
again before completing this merge. This additional integration did not overwrite
or absorb uncommitted work in the other task checkouts.

Final concurrent-entry integration: 115 Python checks passed. One fidelity ancestry
check failed before merge completion because the incoming feature commit was not yet
an ancestor of main HEAD; rerun it after creating the merge commit. All 49 combined
Node tests passed. Review found the incoming late desktop grid rule overrode the
narrow single-column rule (390px columns measured 24px/310px). Moved those desktop
properties into the earlier base rule, preserving both desktop intent and existing
responsive overrides. Browser verification now measures one 354px column at390px,
one 576px column at800px, and 586.25px/351.75px columns at1280px. Terminal snapshots
were refreshed after the TextArea integration. Added the actual incoming inquiry-entry
commit and its review/plan to the existing runtime-interface fidelity mapping.

Merged into main as `367a84a` after the final independent review approved the HTML,
TextArea adaptations and responsive CSS correction (49 browser tests and 12 focused
Python tests independently passed). Post-merge, the ordinary fidelity generator and
all 17 matrix checks passed in 1.53 seconds; the public-file scanner passed. Its
pre-merge ancestry failure and the generator's identical pre-merge failure were
resolved by the real merge ancestry, without disabling validation. The actual incoming
inquiry-entry commit is now mapped and both JSON copies/reports are synchronized.
The final preview runs from main using an empty synthetic store. Main is left with
committed source, review and validation evidence; no paid research or live SSH ran.
