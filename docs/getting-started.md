# Getting started with Metis

[Documentation](README.md) · [User guide](usage.md) · [Troubleshooting](troubleshooting.md)

Start with the offline demo to see the research record. Then configure a model and
compute before starting a live inquiry. Metis is an experimental preview: a completed
demo or passing setup check does not establish scientific capability.

## 1. Install

You need Git, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Install uv using its official instructions for your operating system. The first sync
needs network access to download Python if needed and the locked dependencies.

```bash
git clone https://github.com/tadteo/Metis.git
cd Metis
uv sync --frozen
uv run --no-sync metis --help
```

Run subsequent commands from this checkout. `uv run --no-sync` uses its installed
environment; there is no virtual-environment activation step. The package is
`metis-research`, the command is `metis`, and `autoresearch` remains a compatibility
alias. Installation from this repository and its lockfile is the documented path.

The web console and TUI work with the base install. The demo needs no API key,
Docker, GPU or cluster account. Live execution requirements depend on your chosen
[backend](execution-options.md); managed SSH requires a POSIX client and host.
CI checks Python 3.11 and 3.12 on Linux; the native macOS sandbox has separate
recorded runtime checks. A Windows live-execution walkthrough has not been validated.

## 2. Run the offline demo

```bash
uv run --no-sync metis demo
uv run --no-sync metis status
```

`demo` creates and runs a synthetic study immediately. It prints a run identifier
and records experiments in your private state directory. Agents, hypotheses and
review scores are scripted; the regression experiments run locally on synthetic
data. This exercises software behavior and makes no paid model calls.

Open its record in either interface:

```bash
uv run --no-sync metis serve
```

Visit [http://127.0.0.1:8765](http://127.0.0.1:8765) and select the saved demo. Keep
the server running while you use the page. To use the terminal interface instead:

```bash
uv run --no-sync metis tui
```

Opening either interface does not start research. Use the same state directory to
see the same records. See the [user guide](usage.md) for views and keyboard controls.

## 3. Add model access

In the web console, open **Settings → Available to Metis → ＋ Add provider**.
Select a provider and models, choose your free or paid plan, paste the key into
**API key**, choose **Keep key**, then **Add to Metis**. Repeat for additional
providers. Use **Configure → Save model** to edit an existing model. For a local
compatible server, enter its endpoint and exact served model ID.

Metis stores keys in the controller host's supported OS vault, or explicitly for
the current server session when the vault is unavailable. On an SSH controller,
configure the key on that remote host. Session keys disappear when the server stops.
Settings and run configuration contain credential references, not the key itself.

For terminal setup:

```bash
uv run --no-sync metis setup
uv run --no-sync metis settings preset list
uv run --no-sync metis settings check
```

`setup` guides model and compute settings without starting research. The preset
list contains model IDs, source dates, limits and data-use notes. See
[adding providers](usage.md#add-providers-from-presets) for exact CLI examples and
[model routing](model-routing.md) for eligibility, prices and selection policy.
Native Anthropic models need an OpenAI-compatible model alongside them for writing
roles; see the [writer guide](paper-orchestra.md).

An environment variable is another supported credential source. Set the variable
named by the selected provider before launching Metis, using your secret manager.
`.env.example` lists supported names; `.env` files are **not loaded automatically**.
Never put keys in config JSON, a research question, a committed file or a screenshot.
Local key detection does not test provider authentication or model entitlement.

## 4. Choose compute and prepare manuscript writing

Docker is the default experiment backend and needs a running daemon. In the browser,
choose compute during **New research → Project → Execution → Review**. In the TUI,
use **Settings → Execution**. Choose a backend available on the controller host:
Docker, Podman, Apptainer, the native sandbox, Slurm, or explicitly enabled local
execution. Supply the project's dependency image or Python environment where needed.
Read [execution options](execution-options.md) for isolation, GPU access and limits.
Selecting a backend does not install every dependency needed by a scientific task.

For cluster work, follow [managed SSH connections](remote.md) before choosing Slurm.
Keep workspaces on storage visible to compute nodes and the SQLite database on
persistent storage local to the controller, with compatible locking.

Live manuscript stages additionally require the pinned official PaperOrchestra
runtime, reference assets and configured writing/search/image access. Follow
[writer setup](paper-orchestra.md#setup) before expecting a full manuscript and PDF.
Default native Google search/image access requires `GEMINI_API_KEY` in the
controller's launch environment, even if its text-model key is saved in the vault.
The writer has separate execution settings; changing the experiment backend does
not change them. Missing prerequisites leave a diagnostic, resumable stage.

## 5. Create and start an inquiry

Choose **New research**. Enter a specific question, optionally attach papers and
select an existing project folder, then set a model budget. Leave the folder blank
for a managed workspace. Paths and copies belong to the controller host. Review
the selected inputs for private material and secrets.

Choose **Check setup**, address its errors, and inspect its warnings. Create the
run and review the saved configuration. Creation saves an idle inquiry without
model calls. **Start**, **Step** or **Resume** explicitly begins work and can incur
model and compute charges. A step can include several calls or a long experiment.

For the CLI, after configuring settings:

```bash
uv run --no-sync metis new \
  --objective 'Does the reference method generalize to held-out data?' --budget 25
uv run --no-sync metis status RUN_ID
uv run --no-sync metis run RUN_ID --steps 1
```

Replace `RUN_ID` with the identifier returned by `new`. Add `--paper` for a PDF,
text file, URL, DOI or arXiv ID; repeat it for several papers. Add `--project` for
an existing project folder. The agents inspect admitted inputs, retrieve literature
and prepare the baseline and protected measurement protocol. Missing access or
evidence can require clarification; answering does not resume execution automatically.

The monetary budget covers model calls, including intake and preparation, using
configured prices and observed or conservative usage estimates. It excludes
compute, storage and other external charges. Check the provider's own account
limits and [Metis accounting](accounting.md). Free-tier availability and model
quality vary; neither a preset nor setup validation guarantees a completed study.

## 6. Inspect, pause and resume

Use **Research** to inspect stages, experiments, activity and manuscript versions.
Full receipts retain failed commands, rejected ideas and negative measurements.
Pause stops at a checkpoint; a current call or experiment can finish first.

```bash
uv run --no-sync metis pause RUN_ID
uv run --no-sync metis status RUN_ID
uv run --no-sync metis resume RUN_ID
uv run --no-sync metis export RUN_ID summary.json
```

`resume` starts work again. Budget updates and answering a clarification do not.
Exports contain metadata by default; `--include-private` requires review before
sharing. Private state defaults to `~/.local/state/autoresearch`. To use another
location, place `--state-dir DIRECTORY` **before** the command on every invocation.
Do not place private state inside the public repository. Back up the database and
its associated workspaces/artifacts consistently; see [reproducibility](reproducibility.md).

## 7. Update an installation

Pause active research and wait for its checkpoint before stopping the controller.
Back up private state, then update a clean checkout:

```bash
git pull --ff-only
uv sync --frozen
uv run --no-sync metis validate-specs
```

Start the console again. Saved runs retain their configuration and behavior identity;
an upgrade can refuse a resume when behavior or package source changed. Keep the
original recorded installation available for those runs. Do not clear a checkpoint,
delete an attempt or adopt current behavior just to bypass drift. See
[behavior identity](reproducibility.md#ai-behavior-identity) and
[troubleshooting](troubleshooting.md#saved-runs-and-upgrades).

For contributors, use the evaluation extra and complete checks in
[CONTRIBUTING.md](../CONTRIBUTING.md). For all command flags, read the generated
[CLI reference](cli.md). For scientific limits, read the [fidelity report](fidelity.md).
