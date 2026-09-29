# Independent review: Metis inquiry workspace

Reviewed against `38910cb` in an isolated review checkout. Scope: the interface voice,
shared palette, question-led startup, visible terminal navigation, settings retention,
readable evidence projections and compatibility with existing SSH controls. Scientific
engine contracts, prompts, evidence promotion and saved configurations are unchanged.

## Findings

1. **P1 — Constrain the reading viewport so evidence remains reachable.**
   In `tui.py`, `.reading { height: auto }` expands the `VerticalScroll` to its content
   rather than the available research pane. At 80×24, the Overview record title renders
   at row 30 and its raw text at row 32. Every ancestor capable of containing it has
   vertical scrolling disabled; `scroll_visible()` does nothing and clicking the
   record title raises `OutOfBounds`. Experiments/Activity initially show the collapsed
   title at row 20, but expansion puts raw receipts at row 26 outside the screen.
   Use a bounded scroll viewport and test scrolling/opening the complete receipts,
   not only that the widgets remain mounted.
2. **P2 — Avoid pre-layout title truncation.** `_refresh_selected()` measures
   `#main.size.width` during mounting, when it is zero, reducing every title to eight
   characters. A saved “Saved project” opens as “Saved p…” even at 120 columns until
   another refresh. The existing checkpoint-opening test reproduces this. Use an
   initial viewport-based fallback or refresh after layout.

## Independent checks

- Focused TUI/appearance/inquiry suite: 29 passed, one failure (finding 2).
- Browser Node suite: 31 passed.
- Additional terminal probes at 80×24 and 120×40: visible primary destinations,
  all eight settings buttons, and the four research tabs fit their viewports;
  command-palette Escape restores the previously focused settings input.
- Readable projections retain diagnostics and the existing complete receipt/trace;
  untrusted output still passes through redaction/control stripping and literal text
  widgets. The inaccessible viewport in finding 1 must be fixed before accepting this.
- SSH form/actions remain mounted with existing identifiers; the focused TUI suite
  includes remote profile/connect/disconnect, masked MFA and responsive-worker tests.
- Welcome questions populate setup without creating or executing a run. Hidden-start
  guards and existing explicit create/start boundaries remain intact.

No paid research, live SSH, or scientific capability evaluation was performed.
## Resolution and revalidation

The author changed `.reading` to `height: 1fr` and added a viewport-width fallback
when the main pane has not been laid out. Both changes were synchronized into this
independent checkout and re-reviewed.

- Six targeted tests passed: all inquiry-interface tests, including the new actual
  compact record click/expand/scroll regression, plus the existing checkpoint-opening
  test that previously failed.
- An independent scroll probe confirmed that the 80×24 Overview viewport now has
  vertical scrolling enabled; its record title moves into view and can be clicked.
  Experiment and Activity receipt expansion likewise exposes scrollable content.
- The original eight-character initial title failure is resolved.

No actionable findings remain in the reviewed scope. Approval is contingent on the
coordinator completing the planned frozen-source full suite and release checks.
This review does not certify scientific research quality or live SSH behavior.
