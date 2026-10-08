# Review: TUI event times in local time

Plan: [tui-local-time](../plans/tui-local-time.md). Base `d9357f3`; reviewed commit `603ee79`.
Reviewer: independent subagent (not the implementer), read-only, against AGENTS.md,
docs/development.md, VIBE.md and CONTRIBUTING.md.

Verdict: approve, no blocking defects. Re-review of the resolutions (`603ee79..6006c96`, fixes in `dc1a7e2`) also approved; report and web tests 86 passed. Reviewer confirmed aware/naive/invalid handling, DST via
per-instant `astimezone()`, unchanged machine-readable records (`#event-detail` JSON and
`recent_model_calls` keep raw ISO `+00:00`), no other raw UTC slicing in tui.py, cli.py,
system_view.py or tui_temple.py, and the full `tests/test_tui.py` passing under a non-UTC `TZ`.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | Low | Test used `TZ=Europe/Stockholm`, which needs system tzdata; minimal CI would silently use UTC. | Fixed: POSIX rule `CET-1CEST,M3.5.0,M10.5.0/3`, no tzdata needed. |
| 2 | Low | `report_reading.report_document` wrote the raw UTC ISO time as **Recorded** in the console's stage report, while the report list shows local time. | Fixed: server-rendered document has no viewer zone, so it now states the time with an explicit label (`2026-10-01 12:00:00 UTC`). Regression added to `tests/test_report_reading.py`. |
| 3 | Nit | `event_reading` rendered a `None` timestamp as "None" (pre-existing). | Fixed: `value.get("timestamp") or ""`. |
| 4 | Nit | Event reading shows local time above the complete JSON record that keeps `+00:00`. | Accepted: the complete record is the original receipt; its offset is explicit. |
