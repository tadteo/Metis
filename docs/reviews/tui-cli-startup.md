# TUI CLI startup review

Reviewer: independent providers/execution subagent, read-only review of the current repair.

Scope: remove duplicate `tui` registration, align `--run` with `run_id`, use the current
`ResearchApp` constructor, remove the obsolete launcher branch, and add CLI regression coverage.

Result: no actionable correctness findings. The reviewer confirmed one registration and one
dispatch path, preserved fidelity/evaluation commands, current constructor compatibility, and
no research execution in the regression tests. The reviewer independently exercised an unknown
run ID: exit 1 with a normal `run not found` CLI error, without mounting the UI.

A help-text wording nit was resolved: `--config` now describes loading configuration for new
projects, consistent with the current implementation. This review does not certify unrelated
concurrent backend or TUI changes.
