# Automatic project file selection in setup

Base: `cbdd55c`. The setup review still exposes `project.include` when a saved
include pattern no longer matches the chosen folder. This is an internal snapshot
rule, not a decision a new researcher should have to make.

Keep the project folder as the human choice. During browser Check setup, Metis
repairs a stale file selection within its existing bounded, safe inventory. Present
this as inspecting project files. If the folder is empty, inaccessible or too large
for safe automatic selection, ask for a suitable project folder in plain language.
Do not suggest editing `project.include` in ordinary setup guidance. Preserve the
read-only CLI/TUI preflight and the advanced configuration escape hatch.

User journey: choose a project folder, Check setup, inspect the automatically
selected files in Review. A stale include pattern should disappear without a manual
step. An empty or excessive folder should lead to Project with a concrete reason.
Affected surfaces: shared readiness guidance and browser setup/review; no scientific
stage, experiment execution or engine snapshot rule changes.

Acceptance: source repair and nonrepair cases in Python and browser tests; relevant
repository checks; GUI light/dark and narrow/desktop visual/keyboard inspection;
independent review; commits and merge. Record evidence and limitations below.

## Implementation and validation record

Shared preflight keeps the safety and reproducibility checks and now returns the
actual selected filenames in a 200-name preview with the total count. Browser
Review displays that resolved list. Check setup repairs both a selection that
matches no files and a partial selection that hides an existing command script.
An empty, unreadable or excessive folder leads to Project with a plain reason;
it does not expose `project.include` in the ordinary guidance. Advanced JSON
remains available for specialist overrides. The automatic inventory retains
its 200-file and 2 MB text bounds. No research or project command runs in setup.

Independent review found a misleading glob display and a partial-selection
recovery gap. Both were fixed and covered by regressions; the final read-only
review found no remaining actionable issue. See the review record.

Affected checks before final integration: 124 setup/source-policy/web Python
tests and 64 browser logic tests passed. Ruff lint/format, mypy (72 source
files) and `git diff --check` passed. The first full-suite attempt had one
failure from an exact old success-message expectation; its test was updated.
The second full-suite attempt had 908 passes, 3 skips and one behavior-drift
failure because `setup.py` was edited while that suite was running. These
failures are preserved here. The stable committed tree passed the full suite:
910 passed, 3 skipped in 296.46 seconds. The final browser suite passed 64
tests; Ruff lint/format, mypy (72 source files), spec validation, public-file
scan, `git diff --check` and 17 fidelity-matrix tests passed. Feature commit:
`80d906c`; matrix evidence commit: `1532756`.

Visual and keyboard QA used a disposable loopback server and synthetic local
folders. In dark and light themes, and at desktop and 420-pixel width, the
review showed the empty-folder guidance readably and kept Create disabled.
Open project returned focus to the folder field. With two synthetic source
files, expanding Review showed `evaluate.py` and `train.py` as resolved names,
not wildcard patterns. No live run, benchmark or model call was started.
