# Runtime inspection surfaces independent review

Reviewer: `workflow_audit`, independent from implementing agent `workflow_review`.
Scope: branch `codex/runtime-inspection` against `8ad2d49`, excluding scientific source
inspection, agents, engine, prompts, writer and review code.

The reviewer checked TUI startup/shutdown, saved-run inspection without execution, CLI
registration and configuration forwarding, browser/API paths, artifact integrity and CI.
The initial review found one blocker: removing a registered artifact let a later write reuse
its historical path. A regression failed before the fix. Store now resolves the registered
path first and refuses writes if its historical file disappeared. The reviewer inspected
the final guard and independently passed the missing/tampered/version tests (3 in 0.18s).
No blockers remained in this scope; the reviewer approved committing the integration.

Independent checks: 35 TUI/CLI/Store tests, 20 web tests in 10.59s with loopback binding,
and 6 Node browser tests passed. Implementation checks: the combined runtime suite passed
62 tests before the final review regression; the final Store/security/web suite passed
41 tests. Focused Ruff and formatting (10 files), mypy (5 source files), secret scanning and
`git diff --check` passed. A public CLI TUI smoke opened in a PTY and exited with Ctrl+Q,
status 0, leaving zero research runs. The shutdown-timer regression first reproduced
`NoMatches` on a stopped app, then passed after the guard.

Known integration dependency: the frozen fidelity JSON references separately integrated
source audit, integrity, Laya and statistics artifacts. Its full path-resolution test remains
intentionally active and fails until root combines those branches and updates the final
commit/evidence matrix. This review does not certify that unfinished matrix integration,
scientific parity, live-model behavior or real LaTeX compilation. The UI implementation
is tested offline against persisted Store state and real loopback HTTP boundaries.
