# Show TUI event times in the user's local time zone

Base: `d9357f3`.
Branch: `codex/tui-local-time`, isolated worktree.

## Finding and intended boundary

For the same run, the web console showed "Last checkpoint: 07/10/2026, 12:41:46" (browser local
time, CEST) while the TUI Recent activity list showed "10:41:46". Stored event timestamps are UTC
ISO strings (`store.now()`). The browser formats them with `toLocaleString` /
`toLocaleTimeString` in `static/app.js`; the TUI sliced the raw string (`timestamp[11:19]`) in
`tui.py`, showing UTC without a label. The event detail reading (`tui_reading.event_reading`)
printed the raw ISO string. Quota-wait text (`quota_wait.status_message`) already converts to
local time.

Make the TUI match the browser: convert stored UTC timestamps to the system local zone before
display. Add one shared formatter in `tui_reading.py` and use it for the Activity table, Recent
activity and event detail. Stored data, JSON receipts, the complete event record and the browser
are unchanged. Missing or unparseable values keep their original text rather than inventing a time.

Affected journey: Research → Overview (Recent activity) and Activity tab (table and event reading)
in the TUI. Copy is unchanged apart from the time values; no new labels are needed because both
surfaces now consistently show local time.

## Acceptance and evidence

- Regression: a UTC timestamp renders in local time through the TUI formatter (fixed non-UTC zone
  via `TZ`), including naive/invalid input handling. Fails before the fix.
- Focused `tests/test_tui.py`, Ruff, format, mypy on touched modules, public-artifact scanner.
- Behavioral: `AUTORESEARCH_HOME=$(mktemp -d) uv run metis demo`, then compare event times in
  `metis serve` and `metis tui`.
- Independent review recorded under `docs/reviews/tui-local-time.md`.

## Implementation and verification

- Regression `test_event_times_render_in_local_time` failed before the fix (formatter absent) and
  passes after. `tests/test_tui.py`: **25 passed**. Report and web selection: **108 passed**.
  Ruff, format, mypy on the three touched modules and the public-file scanner passed.
- Behavioral (TZ Europe/Stockholm, CEST): after `metis demo` in a temporary `AUTORESEARCH_HOME`,
  the last stored event was `2026-10-08T13:26:44.758508+00:00`. The TUI Recent activity showed
  `15:26:44`, and the `metis serve` console showed "Last checkpoint: 08/10/2026, 15:26:44" and
  `15:26:44` in its activity list. Before the fix the TUI sliced the string and showed `13:26:44`.
  Port 8765 was occupied by an unrelated process, so the console ran on 8791.
- Visual inspection was limited to text values in the Overview and console activity; layout is
  unchanged (same eight-character time column), so 80×24 / theme screenshots were not retaken.
- Independent review and resolutions: [docs/reviews/tui-local-time.md](../reviews/tui-local-time.md).
  Review finding 2 extended the boundary to the stage-report document, which now labels its time
  `UTC` explicitly because the server cannot know the viewer's zone.
- Full suite: **1239 passed, 7 skipped, 1 failed**. The failure,
  `test_evaluation.py::test_prepared_tasks_register_their_metric_units_and_outputs`, raises
  "Install the pinned evaluation extra" because the local environment lacks `--extra evaluation`
  (CI installs it). It fails identically on base `d9357f3`, so it is unrelated to this change.
