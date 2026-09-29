# Standalone execution programs

These ordinary Python sources are packaged with Metis and copied into private
workspaces by `runtime_support.program_source`. They are not prompt templates and
are never interpolated with model-authored code. The allowlisted loader reads source
without executing it. Each entry point has a main guard; execution uses the existing
argv, environment, resource, evaluator and receipt policies in `Executor`.

| Program | Responsibility | Materialized name |
|---|---|---|
| `slurm_runner.py` | Trusted argv worker; bounded logs, workload/evaluator sequencing and process cleanup | `.autoresearch-slurm-runner.py` |
| `demo_benchmark.py` | Deterministic synthetic polynomial-regression fixture | `benchmark.py` |
| `evaluation_model.py` | Public-task nearest-centroid/ridge baseline, editable by the research agent | `model.py` |
| `evaluation_train.py` | Fixed input/protocol loading and prediction output | `train.py` |
| `evaluation_scorer.py` | Protected targets, finite output/seed/split validation and scoring | `evaluate.py` |

The training entry point imports `model.py` from its materialized workspace. Program
files use the Python standard library only; dataset preparation separately requires
the optional evaluation dependencies. Do not import them as platform services.

`tests/test_program_assets.py` pins synthetic measurements from the pre-extraction
program, validates source availability and tests invalid scorer outputs. Existing
execution tests launch the real Slurm worker with a simulated scheduler; evaluation
tests execute both registered public datasets. The demo is synthetic and none of
these checks establish research capability or ScientistTwo benchmark parity.
