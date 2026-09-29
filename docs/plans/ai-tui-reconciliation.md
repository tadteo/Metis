# Rich TUI and AI inspector reconciliation

Base: writer-reconciled `f9bfc29`; frozen rich interface: `aeb24aa`. Preserve the current
AI-native behavior inspector while porting the concurrent richer terminal interface:
setup/config source, task-specific parallel workers, budgets, evidence/artifact browsing,
readonly archived prompts, responsive checkpoint-aware shutdown and corrupt-run isolation.

Root owns setup/CLI `config_path` propagation and final documentation integration. This
branch owns `tui.py` and TUI tests. Use `behavior.describe`/recorded behavior bundles for
routing and agent policies instead of duplicating model precedence in interface code.
Preserve real source/provider/native/disabled model identity and full research history.

Compare frozen implementations, reconcile IDs and regression fixtures, then exercise
headless Textual pilots and affected CLI tests. Run Ruff/mypy and public scanning. Obtain
independent root review before meaningful commits; do not treat UI tests as scientific
capability evidence.

## Completion evidence

The source reconciliation and behavioral fixtures are implemented. Independent review
approved the diff; see [the review record](../reviews/ai-tui-reconciliation.md). The
coordinator integrates the small CLI fixture/`config_path` changes owned by that branch
and runs the combined suite after merging. No paid providers or live experiments ran.
