# Stage reports independent review

Base: 236da46. Reviewer: separate read-only agent `review_stage_reports`.
Final result: approved; no remaining correctness, privacy, transaction or scientific
acceptance blocker. Reviewer independently ran the five report tests and browser
report regression. Software behavior only; no research-quality claim.

Findings resolved:
- Internal checkpoint saves hid observations from exit deltas. Engine.step now
  captures the attempt-entry state; outcome saves use that snapshot.
- Writing stages omitted their main output. Reports now retain manuscript SHA-256
  and byte length without copying its entire text.
- Incoming reports replaced expanded detail DOM and lost keyboard focus. The
  selected report detail is retained until the selected identity changes.
- Pending coding reasons were absent. Outcome reasons are now recorded and shown.

Visual acceptance used only a public synthetic fixture: desktop charcoal and cream,
390px viewport with document width/scroll width both 390px, keyboard report selection,
evidence expansion and visible focus. Screenshots: ../evidence/stage-reports/.
Blocked and successful checkpoint reports were read; legacy/empty and waiting/budget
states are covered by deterministic checks. No TUI layout changed.

Unsuccessful validation attempts are retained here: the initial test used a nonexistent
stage enum; the HTTP fixture initially referenced a nonexistent server.engine; both
were corrected. Review repair briefly omitted the reason parameter, caught by lint/type
checks, and the internal-checkpoint fixture lacked a required limitation. The first
full-suite run overlapped those edits and is not final evidence. No scientific
measurements or provider calls occurred.

The initial overlapping full-suite invocation ended with 1032 passed, 3 skipped,
and 4 failures: three source-provenance guards correctly blocked runs when the
implementation changed during execution; the fourth was the corrected HTTP fixture.
A separate stable-source full run is the acceptance run. The packaged wheel smoke
passed (1 test), the full synthetic demo completed, all 99 browser checks passed,
and Ruff, formatting, mypy (85 modules), spec validation and public-file scan passed.

Final stable-source full suite: **1038 passed, 3 skipped** (351.77 seconds).
Focused backend/API report checks: **6 passed**. The earlier failures do not recur.

Integration with main through d0e2fd8 preserved execution choices, blocked-run guidance
and their tests. Append-only conflicts in usage and browser tests retained both sides.
Independent reviewer approved integration and reran 95 web UI tests; all browser
suites together passed 102 tests. Merged backend/API/settings/process checks: 98 passed.
Fidelity matrix: 17 passed. Merged Ruff, formatting, mypy and public scan passed.
The merged browser was also inspected: recovery guidance and Stage reports coexist.
