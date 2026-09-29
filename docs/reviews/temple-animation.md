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

## Integration re-review

Reviewed automatic merge `6e9bde1` against feature commit `767fb78` and integration
base `d890295`, focusing on `docs/usage.md`, `static/index.html`, `static/style.css`,
`static/app.js` and `tests/test_web_ui.mjs`. No actionable integration finding.

Both reviewed changes survive: the Home scene, accessible local controls and narrow
layout coexist with the simplified model-access setup, question-derived run naming,
credential-variable guidance and updated entry copy. The merged `app.js` is byte-for-byte
identical to `d890295`; temple script/scene are identical to `767fb78`. The HTML keeps
both control sets and their distinct IDs, CSS additions remain scoped to their own
surfaces, and the user guide retains both workflows. No new shared listener or
research-execution coupling was introduced by the merge.

Refreshed the five integration files in the isolated review checkout and independently
ran `node --test tests/test_web_ui.mjs`: **48 passed**, including both setup and temple
regressions. `git diff --check` passed. Integration approved; prior visual and terminal
findings remain resolved because their renderer/widget files were unchanged.

## Final concurrent inquiry-entry integration

Inspected the in-progress primary-checkout merge of `6e707f1` and `8ee44cb`, including
`docs/plans/inquiry-entry-refinement.md`, the resolved HTML working file and the
TextArea test adjustments. No source edits were made by this reviewer.

The HTML preserves the question-first heading, multiline labelled entry, status
feedback and explicit Continue to setup action from inquiry-entry refinement, together
with the temple fallback/canvas/accessibly named controls. The app handler remains
identical to the incoming entry revision; it rejects blank questions and opens setup
without creating research. TUI changes retain the same handoff contract. Updating
`tests/test_temple.py` to TextArea `.text` and `tests/test_inquiry_interface.py` to
`.load_text()` matches the changed widget while preserving no-research-side-effect
and input-scope assertions.

**P2 — narrow Home question column collapses after the automatic CSS merge.**
`src/autoresearch/static/style.css:406` adds a late two-column `.welcome-hero` rule
after the existing max-800px single-column breakpoint. At 390px, actual Chromium
computed columns are 24px/310px and the question textarea is only 28px wide. The
page still has no horizontal overflow, so that check alone misses the unusable entry.
Restore a single-column override after the late desktop rule at narrow widths.
Resolution: coordinator moved the desktop grid/padding into the original base
rule before the responsive breakpoints and removed the late duplicate. Independent
Chromium recheck confirmed single-column layouts at 390px and 800px (textarea
widths 332px and 554px), and the intended two columns at 1440px (textarea 664px).
All three document widths equal their viewports; the rendered question and continuation
action are readable. The review rendering used static HTML/CSS with the packaged
fallback; the previously checked renderer code is unchanged.

Independent merged browser logic suite: **49 passed**. Focused terminal/inquiry
integration suite: **12 passed in 21.42s** (`tests/test_temple.py` and
`tests/test_inquiry_interface.py`), including the TextArea handoff and scoped temple
keys at 80×24/120×40. `git diff --check` passed in the review checkout.

Final concurrent integration **approved after the responsive correction**. Reviewed
working-file SHA-256 prefixes: HTML `47615a893b296602`, CSS `cceeeb877b82d417`,
app JS `341ff0d3ba414209`, TUI `ba2926f9d0f1035b`, browser tests `84d88ef5eea6b1d3`,
temple tests `6e72196635760ae1`, inquiry-interface tests `f4647724dcbb4027`. These
files match the primary working tree. Conflict markers have been removed from HTML;
staging, merge completion and post-merge ancestry checks remain the coordinator's
responsibility.
