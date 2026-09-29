# Final scientific fidelity integration

Base: `d37e7a0` on the isolated `codex/fidelity-integration` branch. Merge the
independently reviewed statistical (`7c1875c`), runtime foundation (`befd101`),
and runtime inspection (`0e68650`) branches, then the reviewed fidelity evidence
matrix. Preserve both implementation intents in conflicts; test the combined
system before merging into main.

Acceptance: ordinary full Python/JS suites, Ruff format/lint, strict mypy, secret
scanner and its self-test, offline executed demonstration, actual pinned upstream
writer tests with deterministic model/compiler fixtures, and reproducible public
data baseline evidence. Independent reviewer checks combined wiring, conflict
resolutions and scientific invariants. Check all frozen concurrent source changes
are integrated or explicitly superseded by stronger reviewed code. Keep original
snapshots recoverable. Review main status immediately before its merge and preserve
unrelated work; do not fold other user-owned AI-architecture work into this task.

Status: implemented and independently reviewed; final combined validation passed
at `9e7880b` (533 Python tests, six browser tests, separate actual-upstream smoke,
static checks and installed-wheel asset verification). See the final review and
`docs/evidence/final-validation.json`. The reviewed main merge follows this validation record in Git history.
