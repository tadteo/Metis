# Readable stage reports review

Base: a21841f. Independent reviewer: separate read-only agent
`review_readable_reports`. Approved initial implementation and final metadata,
download and narrow-table refinements; no actionable security, correctness or
record-preservation findings. Reviewer independently passed formatter tests and
98 web UI tests; its backend HTTP tests were blocked by sandbox socket permission.
Coordinator's escalated formatter/web suite passed **79 tests**; all browser suites
passed **105 tests**. Formatting never makes a scientific judgment or model request.

Verified public synthetic UI: 1280×900 charcoal and cream, 390×844 narrow, semantic
headings/lists/emphasis/table/code/link, keyboard report selection, and original-record
access. Narrow document width stayed 390px while the table scrolls within its bounds.
Screenshots are under ../evidence/readable-stage-reports/. The real downloaded .md
was 1574 bytes and matched the deterministic saved-report projection exactly.

The stored JSON remains authoritative. The read-only endpoint is authenticated and
run-scoped. HTML remains text, images are not loaded and DOM links permit HTTP(S)
only. No innerHTML or CDN was added. markdown-it-py 4.2.0 was already in the lockfile
through Textual; it is now an explicit dependency because the reader imports it.

Unsuccessful checks: the first parser test exposed as_dict's upstream list-attribute
format; explicit native dict attributes fixed the backend/frontend contract. One
un-escalated Ruff call could not write the worktree cache; the escalated check passed.
The browser automation download-event wait timed out, but both actual downloads were
saved; direct file verification established exact Markdown content. A restarted
preview needed reload to consume its new session token. No paid calls or scientific
measurements occurred.

The first complete suite reported 1069 passed, 3 skipped and 2 failures. The remote
bundle's pinned requirements omitted the newly explicit parser dependency; its
existing equality test reproduced this and the list now matches pyproject.toml.
The independent reviewer approved that correction. A terminal worker timing test
failed waiting for its worker to start, then passed unchanged in a focused rerun.
The complete suite is rerun after the dependency correction.

Static validation passed: Ruff check/format (168 files), mypy (86 source files),
spec validation (48 agents / 29 stages), and the public-file scanner. A clean frozen
offline install with the evaluation extra passed. The synthetic CLI demonstration
completed; it verifies software control flow only.

The final wheel build and installed-artifact smoke test passed (1 test). Active
checkouts were inventoried before integration; only this task's worktree had changes.
The temporary synthetic browser tab and preview server were closed after inspection.

Final complete regression suite: **1071 passed, 3 skipped in 334.42s**. Both earlier
failures passed in this run. No skipped check is claimed as passed.
