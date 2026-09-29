# TUI CLI startup repair

User report: `uv run autoresearch tui` raises `argparse.ArgumentError: conflicting subparser: tui`.
The current working checkout had two registrations and two dispatch paths from concurrent
integrations. One dispatch imported a `run_tui` helper no longer present in the current TUI.

Boundary: reconcile only the CLI startup paths; preserve fidelity/evaluation commands and the
current `ResearchApp(store, config, run_id)` contract. Do not replace concurrent TUI/backend work.

Acceptance: top-level and subcommand help construct successfully; the public CLI forwards the
configuration and saved run to the actual application; an unknown run fails before UI mounting;
the exact reported command opens and exits without executing research.

Validation: the four initial regression cases failed with the reported duplicate-registration
exception before repair. The final CLI and current TUI suites pass (six tests). The exact
`uv run autoresearch tui` command opened in a PTY and exited with `q`, status 0. No research ran.
Ruff lint and formatting checks passed for the changed CLI and regression tests.

Integration boundary: this was a narrow repair to the already-dirty shared working checkout.
The extensive concurrent implementation changes were preserved and have not been staged or
attributed to this repair. The normal isolated-branch/commit workflow was not completed; this
record does not claim a reviewed or committed integration of the surrounding backend changes.
Independent focused review is recorded in `docs/reviews/tui-cli-startup.md`.
