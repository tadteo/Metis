# AutoResearch

An independent, extensible implementation of the ScientistTwo research workflow, with a web console, an interactive terminal interface, a scriptable CLI, durable research history and configurable model/execution backends.

This repository implements the research loop described in [ScientistTwo](https://arxiv.org/abs/2609.19644). It is **not an official release or a validated reproduction of the paper's scientific performance**. Live manuscripts use pinned official PaperOrchestra agents; peer review uses the released ScholarPeer Appendix G prompts with reconstructed orchestration. Multi-provider retrieval and iterative coding/inspection retain underlying evidence. Read the [fidelity report](docs/fidelity.md) before using its outputs as research evidence.

## Run it

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). From this checkout:

```bash
uv sync --frozen --group dev
uv run autoresearch serve
```

Open [the research console](http://127.0.0.1:8765). Choose **Create live research** to configure a project, check readiness and create a run. Opening the console, checking configuration and creating a run do not start research or make paid model calls. Execution starts when you explicitly choose Start, Step or Resume.

The setup form edits the source directory, baseline and evaluator commands, protected files, metrics and reference results, model endpoint and credential environment-variable name, execution backend and budget. The advanced JSON editor and import support the full configuration. Readiness checks identify missing setup; they do not establish model availability or scientific validity. Existing runs retain their saved configuration.

Prefer a terminal? The TUI is an interactive screen application; the CLI remains available for scripts:

```bash
uv run autoresearch tui --config project.local.json
uv run autoresearch tui --run RUN_ID
```

The TUI provides run history, a research tree, experiment logs, activity and traces, manuscripts, setup and intervention controls. Both interfaces expose persisted run state. Use the [interface guide](docs/usage.md) for setup, execution controls and inspection. Pausing takes effect at a checkpoint; it does not instantly terminate a running experiment.

To exercise the system without a model account, choose the separate **Offline demo** action or run:

```bash
uv run autoresearch demo
```

The CLI command immediately runs the demo. It executes synthetic regression experiments with scripted agents and review scores, and makes no paid model calls. It does not discover or validate a scientific result. The [public regression example](examples/README.md) is a separate live-model integration task that can incur model charges.

## Start real research

Set `XAI_API_KEY` in your environment using your preferred secret manager. `.env.example` lists supported credential names; `.env` files are **not loaded automatically**.

```bash
uv run autoresearch init project.local.json
```

Edit the generated JSON, or import it into the web setup form. Configure `project.source_dir`, the baseline command, metric directions, the original full-benchmark values in `project.sota`, benchmark restrictions and a protected evaluator. Default live experiments use Docker; prepare an appropriate image and datasets before starting. An API key alone does not make a research project runnable. See [project setup and reproduction](docs/reproducibility.md).

```bash
uv run autoresearch check --config project.local.json
uv run autoresearch new --title 'Public benchmark study' \
  --objective 'Investigate a documented limitation under a fixed evaluation protocol.' \
  --config project.local.json
uv run autoresearch run RUN_ID
uv run autoresearch serve --config project.local.json
```

Use the identifier returned by `new` in place of `RUN_ID`. `new` records the run without executing it; `run` starts execution. `serve --config` supplies the web form's initial configuration, which you can edit before creating a new run. The TUI's `--config` likewise supplies the configuration for new runs; `--run` selects an existing run without starting it.

The default compatible provider targets xAI with `grok-4.7`. Provider endpoints, model identifiers, pricing, output limits and role routing are configuration fields. OpenAI-compatible APIs, OpenRouter and compatible local servers use the same transport. Cheap generative models can be selected through `cheap_provider`. Laya has a separate first-class `/v1/systemone` typed-decision adapter configured with `laya`; it is non-generative and supplies advisory triage rather than writing or coding. There is no bundled model download. Optional frontier routing is configured explicitly.

## Research workflow

```mermaid
flowchart TD
  L[Limitations and independent verification] --> I[Seed ideas and novelty checking]
  I --> B[Reproduce subset baseline]
  B --> S[Subset experiments and engineering]
  S --> F[Full benchmarks and engineering]
  F --> E[Evolve from successes and failures]
  E --> S
  E --> C[Select validated candidate]
  C --> A[Ablations and method refinement]
  A --> D[Manuscript]
  D --> P[Peer review]
  P --> R[Rebuttal experiments and revision]
  R --> P
  P --> M[Meta-review]
  M --> A
  M --> V[Integrity checks and final artifacts]
```

The full stage specification, published iteration limits, stopping conditions, unsuccessful outcomes and assumptions are in [paper-spec.md](docs/paper-spec.md). Scientific rejection and failed experiments remain available for subsequent evolution. Budget limits do not authorize skipping stages or inventing successful outcomes.

## CLI and private state

```bash
uv run autoresearch status
uv run autoresearch status RUN_ID
uv run autoresearch run RUN_ID --steps 1
uv run autoresearch pause RUN_ID
uv run autoresearch budget RUN_ID --usd 50
uv run autoresearch resume RUN_ID
uv run autoresearch cancel-experiment RUN_ID
uv run autoresearch intervene RUN_ID --note 'Check sensitivity to the registered random seeds.'
uv run autoresearch export RUN_ID summary.json
```

Runtime state lives outside the repository at `~/.local/state/autoresearch` by default. Set `AUTORESEARCH_HOME` or the global `--state-dir` option to choose another private location. The SQLite checkpoint, cache, source copies, manuscript and experiment artifacts can contain sensitive research material. Redacted trace mode does not remove the raw state needed for resumption. Exports contain metadata by default; `--include-private` explicitly includes potentially sensitive research content.

`resume` starts execution after clearing a pause or recoverable error. Budget changes do not resume a run. `cancel-experiment` applies to a pending Slurm job after pausing the run; a cancelled run remains paused until you explicitly resume it.

Local execution requires explicit configuration and is not a sandbox. Slurm execution runs with the permissions of the submitting cluster account. The console binds to loopback; use an SSH tunnel to inspect a console running on a remote host. Read [SECURITY.md](SECURITY.md) before connecting private projects or custom tools.

## Develop and extend

```bash
uv sync --frozen --group dev --extra evaluation
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync mypy src
uv run --no-sync pytest
uv run --no-sync python scripts/scan_secrets.py
uv run --no-sync pre-commit install
```

Live drafting runs pinned official PaperOrchestra to produce ICLR 2025 source, figures, bibliography and a compiled PDF when the configured runtime completes successfully. See [writer setup](docs/paper-orchestra.md) for its isolated environment and native grounded-search/image credentials. Peer review executes published ScholarPeer Appendix G prompts with retained questions, answers, cutoff and reviewer outputs. See [architecture](docs/architecture.md), [reproducibility](docs/reproducibility.md), [fidelity and integration gaps](docs/fidelity.md) and [contributing](CONTRIBUTING.md). Provider, agent and executor contracts are typed and replaceable. Use [public-task evaluations](docs/evaluation.md) and `autoresearch evaluate` for fixed protocols, real baseline runs and paired ablations. [The machine-checkable fidelity matrix](docs/fidelity.json) separates implementation fidelity from unmeasured scientific parity. User-configured command adapters remain available for external and held-out evaluators.

Development uses an honest prototype import (`6936a17`) followed by focused, tested and independently reviewed branches. Read [the continuation workflow](docs/development.md) and the component commit/test mapping in [fidelity-report.md](fidelity-report.md). Ordinary CI runs the real-data evaluation fixtures; a separate job installs the hash-locked official writer SDK/source and exercises real agents with deterministic responses. These tests do not certify paid writing, live Docker/TeX execution, reviewer calibration or the original 107-task benchmark.

Released under [Apache License 2.0](LICENSE).
