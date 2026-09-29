# Metis inquiry workspace

Base: 38910cb. Follow-up to metis-interface: user rejected the remaining TUI usability
and supplied an exact muted Kinfolk palette and a calm, precise, gracious scientific
voice. The interface should feel like entering a laboratory/archive of inquiry, with
Greek character expressed quietly, without mysticism or claims of omniscience.

Boundary: interface copy, colour tokens and presentation/navigation only. Do not change
scientific agent prompts, model dispatch, evidence gates, paid execution, SSH semantics
or saved research configuration. Preserve every operation and literal raw receipts.

Plan: implement exact light/dark palette; cream and charcoal dominate controls, with
terracotta reserved for small active indicators. Shared welcome question in browser,
terminal and CLI. Browser home question leads into existing explicit creation flow.
TUI mirrors browser: visible primary destinations, recent saved research on wide
screens, compact navigation at 80 columns; four research tabs and progressive details;
readable overview/experiment/activity pages; visible settings sections and guided
forward/back movement. Maintain focus during navigation and prevent hidden execution.

Acceptance: fresh workspace gives a clear next step; question text survives transition
to setup without creating or starting a run. Browser and TUI use consistent naming and
palette. 80×24 and 120×40 TUI plus narrow web views remain reachable. No modal/menu
focus regressions; raw measurements/errors/receipts retained and untrusted text inert.
Theme changes remain separate from research config. Save partial setup as before.

Validation: focused interaction/regression tests, rendered TUI inspection in both
sizes/themes, browser visual checks, frozen full suite, lint/types/browser tests,
package/spec/scanner/demo checks; independent review in its own checkout. Commit,
update fidelity with actual feature commit and merge into clean main. Record failures.

Implementation and checks: exact supplied palette now drives browser, TUI and CLI.
Question-led home carries text into explicit setup without starting research. TUI
uses wide sidebar/compact primary navigation, four research tabs, visible settings
sections, and readable evidence summaries with complete expandable records. Added
interface voice guide; updated usage and managed connection navigation instructions.

Preserved failed checks: initial TUI render failed because Textual requires two or
four spacing values (three-value CSS corrected). A later focused run had 96 passed /
1 failed: saved-run title was truncated before initial layout. Independent review
also reproduced unreachable expanded records at 80×24. Corrected initial width
fallback and constrained reading scroll containers; new interaction regression
opens each complete record and reaches its bottom. Reviewer rechecked both fixes:
6 targeted tests and 31 browser tests passed; no remaining actionable findings.
Mypy/ruff cache writes initially failed under sandbox; reran using temporary/no cache.

Visual evidence: rendered Home and Settings at 80×24 and 120×40 in both themes,
and Overview/Experiments at both sizes with explicitly synthetic fixtures. Browser
checked at desktop and 390px width: light/dark appearance, question retained in setup,
zero runs created, section navigation and narrow settings controls reachable.
Screenshots stay outside Git; no private research data used. No paid calls or SSH.

Pre-integration inventory: main remains clean at 38910cb. Separate project-onboarding
and onboarding-review checkouts have active changes (including web assets); those are
outside this branch and remain untouched. Other unrelated checkouts were clean.

Release checks passed: Ruff lint and formatting (128 files), mypy (68 source files),
31 Node browser tests, validate-specs (46 agents, 28 stages), public-file scanner and
scanner self-test. Wheel built to an isolated temporary directory; installed-artifact
test passed. Offline demo completed at complete with the explicit outcome
previous_best_retained_meta_refinement_not_superior and no execution error. This is
synthetic control-flow evidence, not research-quality parity. The review checkout was
archived after its signed-off record was copied; the task checkout remains reusable.

Frozen-source full suite: 847 passed, 3 conditional skips in 270.54 seconds. The
installed-wheel check ran separately and passed. No source changes followed the
independent review fixes. Stopped a stale earlier TUI-only test process after its
replacement focused/full suites passed; temporary preview server and browser closed.
