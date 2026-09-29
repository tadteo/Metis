# Rich TUI reconciliation review

Implementation base: `eaf42bf` (the existing AI-system inspector from `51bf438`, on the
writer-reconciled branch). Rich terminal interface source: frozen `aeb24aa`. The port
preserves setup/configuration controls, independent research workers, evidence and
artifact metadata browsing, budget interventions, pause/quit checkpoints, and history.
It adds the immutable run-bundle inspector without copying routing precedence into UI
code; current previews use `behavior.describe` and saved runs use `inspect_run`.

The coordinating agent independently reviewed the complete TUI source delta on
2026-09-29 and approved it before commit. Review confirmed that archived prompts stay
bound to the run, corrupt behavior bundles leave journal inspection usable, model
receipts use the generic accounting representation, and richer worker controls remain
present. The author did not supply their own independent approval.

Focused behavioral coverage includes two simultaneous run workers and checkpoint-aware
shutdown, corrupt saved bundles, archived prompts after local instructions change,
native/disabled/demo model identities, saved routing, redacted evidence display, budget
interventions, and Textual rendering. Ruff, strict TUI mypy, the public-content scan and
`git diff --check` pass. The focused TUI suite passes (19 tests); affected CLI tests found a stale
fixture attribute (`run_id` instead of rich UI `selected_run`), which the coordinator owns
and will update with the CLI `config_path` pass-through. No compatibility state alias is
introduced. Final integration runs both suites together.

These are offline UI and control-flow checks. They do not establish research quality or
ScientistTwo capability parity.
