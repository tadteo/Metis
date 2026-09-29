# Temple refinement

Base: `604b08c`. The user requests removing the browser temple's top/bottom rules,
pause and reset icons, and ground grid; keep only replay in a corner. Simplify the
terminal temple and inspect actual screenshots. Prior direction still applies:
slow vertical construction, no waves or automatic rotation, no visible captions.

Boundary: decorative browser/TUI presentation, scoped controls and usage docs only.
Preserve inquiry entry, scientific behavior and concurrent main's uncommitted HTML
copy changes. Reuse the clean temple-animation worktree on codex/temple-refinement.
Terminal may use lower-detail geometry suited to character cells while preserving
shared timing, palette, user-controlled rotation and reduced-motion behavior.

Acceptance: browser has an unobstructed temple and one corner replay icon; keyboard
rotation/pause/reset remain scoped and accessible. Terminal shows a clean colonnade,
steps and pediment instead of dense block shading, at 80x24 and 120x40. Both themes,
GUI desktop/narrow layouts, pointer/keyboard rotation, offscreen pausing and completed
reduced-motion rendering remain usable. No research state is created by interaction.

Validate focused temple/browser/TUI suites, lint, types and public artifact scan.
Inspect synthetic screenshots, obtain independent review against this base, then
commit, map the actual commit in fidelity evidence and merge. Record failures and
visual iterations here. Full scientific revalidation is unnecessary for isolated
presentation changes; no claim of research quality follows from these checks.

## Implementation and validation

Browser: removed the ground grid and frame rules. Only the accessible replay icon
remains, positioned at the top-right corner. Space and Home remain scoped to the
focused canvas; no visible instructions or automatic rotation were added. Reduced
motion and hidden-tab/offscreen pausing retain their previous behavior.

Terminal: replaced dense per-brick shading with a hidden-line Unicode dot drawing,
using ten columns, two foundation steps, beams and a pitched pediment roof. It uses
large structural pieces with the existing 23-second timing and straight vertical
fall. A fixed completed-scene frame prevents camera movement during assembly. Mouse
and keyboard rotation remain; focus uses accent colour without an enclosing box.
The footer shows only replay among the temple-specific bindings.

Visual iterations discarded an overly detailed wireframe, then reduced columns and
internal edges to make the outline legible. Inspected actual synthetic terminal
screenshots at 80x24 and 120x40, both themes, initial Home and focused/scroll-reached
temple. Inquiry remains the first action. Inspected GUI at desktop and 390px in both
themes, with pointer and keyboard rotation and replay. At 390px, scrollWidth equals
390, frame borders are 0px and the only temple button is Rebuild temple.

An initial HTML edit removed the whole minified controls line, including replay;
visual preview showed the static fallback. Restored the one replay button and
verified the live canvas and animation. Initial terminal outlines were too busy;
face silhouettes and fewer columns resolved this. Two attempted pytest commands
used nonexistent inquiry filenames and collected no tests; corrected to the actual
`tests/test_inquiry_interface.py`. The first preview command used an incorrect server
constructor and was corrected before UI checks. Ruff initially could not write its
cache in the isolated checkout; used a temporary cache. Lint then caught a missing
zip(strict=True), and mypy caught reused point/index variable names; both corrected.

The affected temple/TUI/inquiry/web suite passed 100 tests in 101.65 seconds. All 52
Node browser tests passed; mypy passed across 72 source files and the public-file
scanner passed. No scientific runtime, configuration or external service was changed.

Final renderer recheck passed all seven temple tests after the type-only index-name
fix. Repository-wide Ruff lint and formatting passed (135 files). Initial screenshots
respected this shell's NO_COLOR setting; repeated both themes with a true-colour
terminal environment and inspected the terracotta focus state without a frame.
A fidelity-row lookup initially used id rather than component; corrected the lookup.
Main subsequently committed the separate Home edits as `522e3ae` and is clean at
`df05400`; no stashing or absorption of that work is needed for integration.
