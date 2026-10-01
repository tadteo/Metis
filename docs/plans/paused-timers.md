# Freeze research interface timers

Base: 804c33b. User reports project trace/interface timers continuing while paused
or blocked awaiting Resume research. Scope: read-only process projection shared by
trace totals, stage visits and research overview; preserve measured call/experiment
receipts and operational wall-clock budgets. Exclude recorded pause/block intervals
so resume does not add the idle gap. Keep original timestamps for audit timelines.

Use synthetic Store records and a fixed clock to reproduce refresh growth, then test
resume, repeated pauses, stage transitions, blocked/budget states, and active work.
Run projection/web/browser tests, lint/types and public-file checks, obtain an
independent review, commit and merge. No layout change or paid research execution.

## Evidence

Before fix: `PYTHONPATH=src pytest tests/test_process_view.py -q -k timers`
failed all four cases: a run stopped at 10 seconds displayed 30 at refresh.
Confirmed cause: process projection used captured wall time for every nonterminal
run and current visit; browser only formats the returned values.

After fix: 16 projection tests passed, including actual Engine.pause/resume calls,
cooperative in-flight completion, repeated pauses, blocking, cancellation, terminal
freezing and legacy checkpoint fallback. Related projection/web run: 89 passed
(before adding cancellation parameter); browser suite: 101 passed. Ruff lint/format,
focused mypy, diff whitespace and public-file scanner passed. No layout/style change;
behavior verified through real projection/API and existing browser tests. No new
visual inspection or live deployment claimed.

Historical idle gaps without recorded hold events cannot be reconstructed; fallback
freezes at the latest checkpoint/event while idle. Operational budget wall time and
measured experiment/call receipts retain their existing semantics. Research quality
is not evaluated by this repair.
