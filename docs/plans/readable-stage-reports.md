# Readable stage reports

Source: user says long stage reports are almost unreadable and asks whether they are Markdown.
Base: a21841f. Reuse the clean, merged stage-reports worktree on a new branch.

Keep stored JSON and scientific behavior unchanged. Produce a Markdown document from
an existing saved report on demand, with headings, metadata and readable evidence.
Use installed markdown-it-py for parsing; create safe DOM nodes from its tokens,
never insert raw HTML or load embedded images. Add Download Markdown in the report
reader. Keep source records expandable and preserve report selection during polling.
Read-only authenticated endpoint, no paid model calls and no migration/backfill.

Acceptance: Research → Stage reports → read long headings/lists/tables/code → download
.md; existing reports work. Check malicious HTML/URLs, lossless source access, request
races, keyboard/poll stability, empty/error states and light/dark desktop/narrow views.
Run focused backend/browser checks and repository validation; independent review,
commit, fidelity evidence and merge follow docs/development.md.

## Implementation and evidence

Saved reports stay JSON; report_reading produces Markdown and parser tokens on demand.
The browser safely constructs semantic elements and provides Download Markdown;
source records remain expandable. Existing reports need no regeneration. Narrative
content is formatted, scalar metadata precedes nested evidence sections, and narrow
tables scroll without splitting words. No agent prompts or scientific routing changed.

Independent review approved, including final refinements. Focused Python/API checks:
79 passed. Browser suites: 105 passed. Synthetic browser inspection and exact downloaded
Markdown verification passed. See ../reviews/readable-stage-reports.md for details,
limitations and unsuccessful validation attempts. Full suite: 1071 passed, 3 skipped. Wheel build and installed-artifact check passed.
Static checks, frozen install and synthetic demo passed; no scientific parity claim.
