# Inquiry entry refinement

Base: `d890295`. The user wants the simplified home surface to keep navigation and
main content visually continuous, give the question more room, and make the text
entry action unmistakable. They also requested equivalent terminal UI treatment.

Boundary: browser and TUI home entry presentation plus explicit question handoff into
the existing setup/new-research forms. No run may be created or started from the
question handoff. Existing setup, execution and scientific behavior remain unchanged.

Acceptance: the question is the page's main visual task; the entry is explicitly
labelled with a clear non-executing continuation action; blank input remains in place
with useful feedback; populated input appears in setup/new research without creating a
run; the TUI follows the same rule at 80x24.

Validation: the 47 browser-logic tests and the two focused TUI home-entry tests pass;
Ruff lint/format and diff checks pass. The complete TUI suite was started and showed
passing progress, but the runner's 30-second command window ended before its summary;
the focused regressions then passed in 3.35 seconds. Pytest could not write its cache
in the managed worktree, which does not affect the test result. Independent review is
required before commit.

Visual and interaction evidence: the current browser home was rendered against a
temporary loopback server in charcoal mode at desktop size. The question is the visual
headline, the labelled textarea is visibly larger than the previous single-line field,
and the explicit continuation action remains below its non-execution explanation.
Keyboard/automated interaction checks cover both blank and populated browser/TUI
handoffs; TUI used an 80x24 test viewport. The checked-in responsive breakpoints retain
the existing narrow layout and the existing Cream/charcoal appearance control remains
untouched. A separate manual TUI 120x40 screenshot and theme-by-theme browser capture
were not produced in this constrained run; this is recorded rather than treated as
completed visual evidence.
