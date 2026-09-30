# Sidebar and welcome refinement

Base: `a367ffb`. User requests removing numbered navigation and redundant Home,
moving Settings with a gear beside Getting started, moving appearance into Settings,
reducing home top space, and a larger persistent welcome that fades in above the question.

Boundary: browser HTML/CSS and navigation event binding only. Preserve appearance
persistence, question/setup drafts and scientific behavior. Logo returns home without
reloading. Check desktop/narrow light/dark, reduced motion, keyboard navigation,
Settings appearance persistence and existing browser tests. Obtain independent review,
commit and merge after validation. No scientific component changes.

## Validation

76 browser logic tests pass after final accessibility correction. Public-file scanner
and git diff --check pass. This presentation-only change needs no scientific matrix
update; Python, engine and terminal behavior are unchanged.

Actual Chromium checks used disposable loopback state at desktop 1280x900 and narrow
390x844, both cream and charcoal. Home and Settings render without horizontal overflow
or browser errors. Logo Enter returns home with main focused and preserves the question
draft; appearance persists on reload. Welcome opacity is 1 after its reveal and reduced
motion disables its animation. Six temporary screenshots were inspected; representative
public empty-state captures are retained under docs/evidence/metis-navigation-*.
Existing browser checks cover appearance request failure recovery and setup preservation.

Attempt retained: the initial preview launch was blocked when it tried the default
global settings directory despite --state-dir. Retried with METIS_SETTINGS_HOME pointing
to disposable /tmp state. No actual user settings or research runs were changed.

Independent review by /root/review_navigation found a visible/accessibility theme-label
mismatch, corrected in both initial HTML and dynamic labels. All 76 tests passed again.
