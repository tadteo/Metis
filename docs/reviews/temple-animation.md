# Independent review: self-building temple

Base: `83ab407`. Reviewed in a separate managed review checkout, using a snapshot
of the task files from the author checkout. The reviewer did not edit feature code.
Result: **approved after the two findings below were corrected and independently
rechecked**. Final source/test bytes match the author snapshot.

Scope: complete source/test/documentation diff, including the new shared scene asset,
browser renderer, terminal projection and widget, and the user's preview refinements.

## Findings and resolution

1. **P2 — terminal foundation clipped at maximum tilt.** The original
   `src/autoresearch/temple.py:68` vertical scale (`height * 2 / 17`) combined with the
   center at `height * 0.70` on line 75 crops the completed temple when the allowed
   pitch reaches `0.8`. At 80×24, the widget's 72×15 content projects the lowest
   vertex to row 16.4427; the same proportional clipping occurs at 120×40. Repeated
   Up presses or downward dragging reproduce it. Fit the completed geometry within
   the viewport at supported rotation angles and add an extreme-tilt regression.
   Resolution: completed-scene bounds now fit the current rotation with a one-cell
   margin, independently of falling blocks. Independent silhouette/extreme-angle
   tests passed (3 passed). Final focused suite passed (70 tests), and actual
   80×24/120×40 screenshots at pitch 0.8 now retain the full foundation with margins.

2. **P2 — animation advances while its drawable content is offscreen.** At the
   initial 80×24 Home layout, the temple region starts at y=21, but its content
   starts at y=22. The scroll viewport ends at y=22 (exclusive), leaving only the
   transparent top border in view. `src/autoresearch/tui_temple.py:69-73` tests the
   outer region, so an independent 0.4-second wait advanced animation by 0.4159
   seconds despite all drawable cells being clipped. It can finish before the user
   first scrolls to the art. Intersect drawable content against ancestor content
   viewports and test the initial small-screen wait followed by focus/scroll.
   Resolution: visibility now uses the drawable content region against screen
   and ancestor content viewports. The size-parameterized regression proves zero
   elapsed time before first focus at 80×24, then build/pause/navigation/resume
   behavior at both supported sizes. Independently rerun successfully.

No other actionable correctness, security, scientific-state or input-scope finding
was identified in this snapshot. Source inspection confirms that the scene is
local decorative state, consumes no research progress and makes no research calls.
Static serving preserves the existing Host/Origin boundary and introduces only two
explicit public packaged assets. Shared geometry has 960 finite positive-sized
blocks, ordered course arrival windows, and all stones land before the finite stop.

## Independent checks

- `PYTHONPATH=src .../pytest -q tests/test_temple.py tests/test_web.py`: **67 passed**
  on the user-refined snapshot before corrections; **70 passed in 45.63s** after
  both corrections. Initial
  sandboxed run reported socket-bind PermissionError (4 failed, 57 errors, 6 passed);
  rerun with loopback permission passed. This was environmental, not suppressed.
- `node --test tests/test_web_ui.mjs`: **43 passed** on that snapshot.
- Actual Textual runs at 80×24 and 120×40 in charcoal and cream: initial inquiry
  actions stay visible, focusing the temple scrolls it fully into the viewport,
  controls are scoped to the focused temple, and the footer exposes pause/rebuild/reset.
  The reduced-motion preference yields the completed scene. Examined synthetic SVG
  screenshot data and Chromium-rendered output. An initial sharp rasterization lost
  leading-space geometry in the PNG; the SVG and Chromium render preserve it.
- Actual Chromium pointer and keyboard interactions: pause holds identical canvas
  pixels; arrow keys and mouse drag change the view; replay rebuilds; the 23-second
  animation completes and then holds identical pixels. No POST request occurred
  during these interactions.
- Actual Chromium web rendering at 1440px and 390px in both themes: no horizontal
  overflow (document widths equal viewport widths), inquiry actions precede the
  artwork, architecture remains readable, and icon controls have accessible names.
  Reduced motion shows the final scene and disables animation/replay controls.
  Observed requests use only loopback assets/API; theme clicks make only the expected
  appearance mutation. No research is created or executed.

QA attempts retained: the first projection correction omitted its scale definition
(the author reports 7 failed/4 passed with NameError); the completed correction was
then reviewed and passed the independent extreme-angle checks. The initial offscreen
assertion failed and exposed finding 2. A region-diagnostic helper subsequently
printed the confirming bounds, then failed when it queried a region on the App
ancestor. Browser tooling initially hit an OS sandbox launch denial, an SVG screenshot
font-wait timeout, and an incorrect theme locator based on visible text rather than
the accessible name. Corrected permitted reruns produced the evidence above.

The tests and synthetic visual evidence establish interface behavior, not research
quality or ScientistTwo parity. Full release checks, installed wheel validation and
integration commits remain the coordinating author's responsibility.

Final reviewed implementation fingerprints (SHA-256 prefixes): `temple.py`
`81e6aa7bc5e977fa`, `tui_temple.py` `abf5516ba47e68d4`, `temple.js`
`10448af0fe1ddf56`, shared scene `0065bdaade7184a6`, terminal regression suite
`d54af8a7bedefd18`. The temporary independent review server was stopped.
