# Independent fidelity evidence review

Branch: `codex/fidelity-evidence`, assembled from independently reviewed component
branches; final integration base `dbfca6c` contains `f4ac49d` and its combined review.
No scientific implementation was authored in this task. Its one source merge conflict
retained both approved statistics/source-inspection imports; 67 affected tests passed.

Root independently reviewed the schema, generator, commit/path/test-node validation,
42 component mappings, primary-source boundaries, continuation documentation and CI.
Findings corrected before approval:

- Plot reference provenance belongs to `fa8f15e`, while writer accounting belongs to
  `5a12839` and `d7b006b`; baseline-owned behavior explicitly cites `6936a17`.
- The statistical validator implements Bonferroni correction, not Holm correction.
- The reproduction demo uses `uv run --no-sync` to retain installed evaluation extras.
- Markdown pipe escaping uses a valid escaped string.

Root independently ran matrix, CLI, web and TUI checks: **59 passed in 22.82 seconds**,
then approved the focused commits subject to those documented corrections. The
implementer ran matrix, CLI, TUI and loop checks: **51 passed in 19.47 seconds**;
the final matrix-only regression suite passed **17 tests** after the corrections.
Scoped Ruff, mypy, formatting, diff checks, public-file scanning and scanner self-test
passed. The matrix verifies every cited commit is an ancestor and every referenced
implementation/test/evidence file exists, with named Python test functions resolved.
Both JSON copies and generated Markdown reports are synchronized.

CI retains evaluation extras and adds a separate actual pinned official writer
source/SDK smoke job with deterministic model responses and fixture PDF generation.
The same upstream/recovery tests were run independently by root: ten passed in the
actual locked SDK environment. This task did not execute a hosted CI run, paid models,
real TeX or Docker, and claims no calibrated review or scientific capability parity.
The dated live literature smoke/recheck is inherited evidence, not a new request.

The machine-readable source of truth is `docs/fidelity.json`; generated reports must
be refreshed with `scripts/update_fidelity_report.py`. The remaining exact upstream
ScientistTwo code/prompts and ScholarPeer runtime/few-shot content were not located
in the recorded primary-source audit. Published behavior is implemented; unmeasured
research performance is kept separate from absent public artifacts.
