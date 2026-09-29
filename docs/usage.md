# Using Metis

Choose the web console for visual project setup and artifact inspection, the TUI for an interactive terminal session, or CLI commands for scripting. They use the same private store and saved runs. Launching an interface does not start research.

For a project on an SSH host, use **Connections** in the web console, the
terminal console's **SSH connections** view, or `autoresearch remote`. The [managed SSH guide](remote.md)
covers saved/new hosts, in-interface MFA, installation, reconnecting and cluster storage.

## The temple on Home

A temple assembles stone by stone as a visual metaphor for inquiry. It is decorative,
not research progress. In the web console, drag the temple or focus it and use arrow
keys to rotate and tilt. The small pause, circular-arrow and home icons pause/replay
the assembly and reset the view. Bricks drop straight down at a steady pace; the
complete build takes about 23 seconds.
It rests after assembly and pauses when offscreen. Reduced-motion browser preferences
show the completed temple without a falling-block animation.

The terminal Home includes an ASCII version below the inquiry actions and shortcuts;
scroll or Tab to reach it on a small screen. With the temple focused, drag or use arrow
keys to turn/tilt, Space to pause, R to rebuild and Home to reset the view. These keys
apply only to the temple. `TEXTUAL_ANIMATIONS=none metis tui` shows it already assembled.
No temple interaction creates, starts or changes research.

## Start from an existing project

In **New research**, choose **Inspect this project**, enter the folder on the server and
what you want to investigate, then **Inspect project**. Metis inventories admitted
files and reads bounded documentation, configuration and source excerpts without
executing the project. It excludes known credential paths, symlinks, outputs and caches;
filename and text redaction rules cannot identify every secret in arbitrary source.
Review the exact excerpts before sharing them with a model. Large projects may need
more context; discovery explicitly reports truncation.

**Preview AI request** prepares a private receipt without contacting a provider.
It shows the destination, exact outbound instructions and payload (including current
project/execution settings), and a separate preparation budget
(default $1, maximum $5). **Send excerpts and prepare setup** authorizes one request,
with retries disabled and a conservative reservation at configured token prices.
The server needs the model credential; preparation can incur charges even when the
provider fails. It does not consume a research run's budget. Receipts retain observed
or estimated usage, failures and raw responses privately. **Previous preparations**
recovers them after reload. A running receipt may represent an interrupted request;
it is never replayed automatically. Verify the provider outcome before requesting
another preparation. A configured cost estimate is not a provider-enforced price cap.

Review the proposal's evidence, questions and blockers. Select suggested settings and
**Apply selected suggestions to form**. This updates only the form and invalidates
previous checks. It does not save defaults, modify source, install adapter drafts or
start research. Cited excerpts must still match before application. AI cannot change
credentials, model routing, budgets, executable permissions or authorize local code.
Draft integration files are displayed as untested text for review and implementation.
They do not satisfy missing evaluator or scheduler requirements automatically.

Choose **Enter experiment details myself** to configure a study manually. Training and evaluation
commands accept ordinary quoted arguments (for example `python3 train.py --split subset`)
or legacy JSON arrays. They are executed directly, without shell expansion or pipelines.
Protected evaluation paths can be entered one per line. Full JSON remains available.

**Check setup** leads with the next useful actions. When a source directory exists,
Metis automatically inspects admitted files and shows unverified command candidates;
it asks for the project folder, provider credential, benchmark reference or host setup
when those cannot be supplied from local evidence. Complete errors and warnings remain
under diagnostics, with manuscript prerequisites separate. Inspection makes no model
call; AI preparation still requires an outbound preview and an explicit paid request.
The review explains the source, commands, model and budget before creating an idle run.
It does not run a smoke experiment. **Start** executes the research workflow, and **Step**
is a workflow checkpoint that may contain several calls or an experiment. Neither means
"one cheap test." Existing settings remain reusable for subsequent research.

Projects with custom GPU batch launchers need a compatible execution integration.
The generic Slurm backend does not adopt existing batch scripts or GPU/node/task
requests; recognized direct or nested scheduler launchers are rejected by setup checks.
This is not a general analysis of arbitrary submission code.
Project discovery and a plausible AI proposal are not proof of a working deployment.

## Configure a live project in the web console

Start from the repository root:

```bash
uv sync --frozen --group dev
uv run metis serve
```

Open <http://127.0.0.1:8765>. **Workspace settings** opens at **Model access** so you can configure the provider once and save it for future runs. The three values are the exact model ID, its OpenAI-compatible API base URL, and an environment *variable name* such as `XAI_API_KEY`. Obtain the key from the provider, set that variable to the key in the environment that launches the Metis server, and restart Metis. On a remote research console, set it on the remote host. The browser clears input that is not a variable name; this field is never used as a credential. The setup check reports whether the server can read the configured variable without displaying its value or contacting the model. A passing check does not establish that the credential or model actually works.

Choose **New research** to enter a question and project folder. Metis uses the beginning of the question as the run name unless you expand **Name this run** and enter another. Model access carries over from Workspace settings. Then configure:

| Input | What to supply |
|---|---|
| Source directory | The project directory on the machine running Metis. This is not a browser file upload. |
| Baseline command | An argument array such as `["python3", "train.py"]`. Paths to project scripts are relative to the experiment workspace; shell pipelines are not supported. |
| Evaluator and protected files | An independent evaluator command and the source paths/globs that agents must not edit. The evaluator writes the configured measurements. |
| Metric and reference result | The primary metric, its maximize/minimize direction and the original full-benchmark reference value. Use advanced JSON for multiple metrics. |
| Provider | Model ID, compatible API base URL and the **name** of the environment variable containing its credential. Set the actual credential in the server's environment. |
| Execution | Docker, explicitly enabled local execution, or Slurm. Select an image containing the needed dependencies and configure dataset mounts when appropriate. |
| Budget | An explicit model-spend limit. Advanced configuration includes call, experiment and wall-clock limits. |

The advanced configuration editor/import covers additional settings, including seeds, full benchmark rules, multiple metrics, agent counts, model routing, Slurm settings and read-only dataset mounts. JSON commands must be arrays of separate arguments. A relative source path is resolved by the Metis process, so an absolute path is less ambiguous when launching from another directory.

Source snapshots always exclude known credential filenames and private tool directories such as `.env`, `.ssh`, `.config` and `.codex`, including when `project.include` uses `*`. Setup checks use the same exclusions. Keep inclusion patterns minimal: filename rules cannot identify every secret embedded in ordinary source or prose.

Run readiness validation and resolve its errors before creating the run. Validation checks local configuration and available infrastructure without paid model calls. Warnings describe remaining uncertainty: a locally valid key or URL does not prove authentication, model availability or schema compatibility, and an installed image does not prove the benchmark's dependencies or evaluation protocol are correct.

Create the run, inspect its saved configuration, and then explicitly choose **Start** or **Step**. Creation records configuration and copies the selected source files; execution can use model credits and compute resources. Configuration is fixed for that run. To change the project, model routing or execution backend, create another run with revised configuration. Budget limits have a dedicated update action.

For an existing configuration:

```bash
uv run metis serve --config project.local.json
```

This fills the form's defaults. It does not change previously created runs. `.env` files are not loaded automatically. See [reproducibility.md](reproducibility.md) for the full project protocol and execution requirements.

## Work in a terminal

Run the guided setup, then open the interactive TUI:

```bash
uv run metis setup
uv run metis tui
```

To open a saved run directly:

```bash
uv run metis tui --run RUN_ID
```

The TUI uses the same saved configuration and checkpoints as the web console and CLI.
Home asks what question brings you here. Enter a question and choose **Begin an inquiry**
to carry it into setup; this does not create or start research. The visible navigation
opens **Home**, **Research**, **Settings**, **Connections** and **Guide**. Wide terminals
also show recent research in the sidebar; compact terminals use a top navigation row.
Selecting saved research opens its overview without execution.

Research has four visible tabs: **Overview**, **Experiments**, **Activity** and
**Manuscript**. Read the question, current stage and next action on Overview; experiment
results and activity have readable summaries with expandable complete receipts.
**Controls** opens execution diagnostics and configuration. **Inspect…**, **Commands**
or **Ctrl+K** opens the searchable navigation, including ideas, models/costs, recorded
AI instructions, artifacts and fidelity evidence. **Settings** shows one section at a
time, retains edits while navigating, and offers full JSON under Advanced. Visible
section buttons and **Back/Next** guide setup. **New research** separates setup checks,
live creation and synthetic demo creation.

| Key | Action |
|---|---|
| Ctrl+K | Search navigation commands. |
| Ctrl+L | Open saved runs. |
| Ctrl+T | Switch charcoal / cream. |
| F1 | Open the getting-started guide. |
| Ctrl+N | Open new-run setup. |
| Ctrl+R | Start or resume the selected run from a research view. |
| Ctrl+S | Run one checkpoint step from a research view. |
| Ctrl+P | Request a pause at the next checkpoint. |
| Ctrl+Q or Ctrl+C | Request a pause, finish the active checkpoint and exit. |

Quitting during a model call or experiment can take time because the active step must finish. Inspect diagnostics before resuming a blocked or budget-exhausted run. The TUI uses Textual and needs an interactive terminal; it does not require a browser or curses.

For scripts, use the CLI:

```bash
uv run metis check --config project.local.json
uv run metis new --title 'Public benchmark study' \
  --objective 'Test a documented limitation under a fixed evaluation protocol.' \
  --config project.local.json
uv run metis run RUN_ID --steps 1
uv run metis status RUN_ID
uv run metis fidelity
```

`check` prints readiness JSON and exits with code 0 when the checked setup is ready, or 2 when errors remain. It makes no paid model calls. `new` only creates the run. `run` executes it; `--steps 1` limits it to one engine step. A step may contain multiple model calls or one long experiment, so it is not a single-call spending limit.

## Inspect AI behavior

Run `metis validate-specs` to validate agent, prompt and workflow contracts without model calls. Use `metis system --role subset` for current instructions, `metis system --mermaid` for the stage graph, or `metis system --run RUN_ID` for the archived behavior bundle. Both consoles expose **AI system** views with recorded instructions, resolved routing, tools, validation and transition gates. These views do not substitute current prompts when an original bundle is unavailable. See [the AI system guide](ai-system.md) for extension and migration contracts.

## Inspect and control a run

The web console exposes the hypothesis tree, experiment metrics and logs, agent activity and saved traces, manuscript versions, artifacts, configuration and budget usage. Select an idea or experiment to inspect its recorded details. Empty views mean that the corresponding stage has not produced an artifact yet; they do not imply a completed research result. Artifact downloads require the local console token and verify the saved byte count and content hash before returning the original file. Downloads larger than 16 MiB must be inspected locally.

| Action | Effect |
|---|---|
| Start / Step | Execute the selected run continuously or for one engine step. |
| Pause | Request a stop at the next durable checkpoint. The current call or experiment can finish first. |
| Resume | Clear a pause or recoverable error and start execution again. |
| Human intervention | Record feedback and, where supported, choose an earlier stage. Pause first; pending experiments must finish or be cancelled. |
| Budget update | Set absolute limits. It does not resume a run or purchase provider credit. |
| Cancel Slurm experiment | Cancel a pending scheduler job after pausing; keep its cancelled receipt and the run paused. |
| Export | Save metadata by default; private export explicitly includes potentially sensitive run content. |

The corresponding commands include:

```bash
uv run metis pause RUN_ID
uv run metis intervene RUN_ID --note 'Investigate the failed seed before continuing.'
uv run metis budget RUN_ID --usd 50 --calls 3000
uv run metis resume RUN_ID
uv run metis export RUN_ID summary.json
```

Private state defaults to `~/.local/state/autoresearch`. Set `AUTORESEARCH_HOME`, or place `--state-dir DIRECTORY` before the command, to use another location. Both interfaces must point to the same state directory to show the same runs. Opening two interfaces is supported for inspection; a durable lease prevents concurrent advancement of a run.

## Try the offline demonstration

The web console has a separate **Offline demo** action. The CLI shortcut creates and immediately executes the complete fixture:

```bash
uv run metis demo
```

The fixture uses scripted agents and real local synthetic regression subprocesses. Its review scores and hypotheses are synthetic; it does not make paid model calls or establish scientific capability. The [public regression project](../examples/README.md), in contrast, is a live-model integration example and can incur model charges.

## Resolve common startup problems

| Symptom | Next action |
|---|---|
| Missing credential | Set the configured environment variable in the shell/service that launches Metis, then restart that interface. Do not paste the key into the JSON configuration. |
| Source or evaluator unavailable | Check paths on the execution host, the source inclusion patterns and protected-file matches. Project data is not automatically uploaded or copied. |
| Docker unavailable or image missing | Start Docker and prepare the configured image. Install research dependencies in that image before running; workload networking is disabled. |
| Local backend disabled | Use Docker, or explicitly opt in to local execution with the understanding that it has the host user's permissions. |
| Slurm tools or workspace unavailable | Launch on an appropriate submit host and ensure the private experiment workspace is shared with compute nodes. |
| Citation verification unresolved | Enable external literature retrieval or supply an independently validating literature adapter. Supplying references alone cannot verify their existence. |
| Budget exhausted | Inspect recorded usage, deliberately raise the necessary absolute limit, then resume. A longer wall-clock limit may also be needed after an extended pause. |

An accepted setup check means no checked local error was found. It is not a successful provider request, benchmark reproduction, external security audit or validation of scientific capability.


## Getting started and workspace settings

Run `uv run metis` for the startup guide, `uv run metis setup` for the
interactive terminal setup, or open `tui` / `serve` and choose **Getting started**.
An empty workspace explains Explore → Prepare → Research, with separate offline demo
and live setup actions. Returning users can reopen the guide at any time (F1 in TUI).
The demo is synthetic; creating a run does not execute research.

**Settings** edits private defaults for future runs. The web form and terminal Settings
view cover source, baseline/evaluator commands, protected files, metrics, data protocol
and provenance, Docker dataset directories, provider credentials by variable name,
execution backend, limits and privacy. Section buttons and Back/Next navigate the browser form; the terminal offers the same section buttons and Back/Next flow.
Import/apply full JSON for all additional settings, including writer installation,
role routing, panel models, token pricing, literature, seeds and source filters.
**Check setup** explains missing local prerequisites and untested external services.
Writer setup can block manuscript stages even when early research prerequisites pass;
follow [the writer guide](paper-orchestra.md). Checks make no model requests.

**Save settings** accepts a structurally valid but incomplete setup so preparation can
continue later. Invalid values and concurrent edits are rejected without replacing saved
settings. In the TUI use **Reload saved** after a conflict; in the web console reopen
Settings to load the latest revision. Preserve any unsaved edits before reloading.
The interactive CLI retains answers when values need correction. Ctrl+C cancels it
without saving. No API keys are stored by setup: export the named variables before
launching, and restart the interface after changing its environment. `.env` files are
not loaded automatically.

Settings persist in the private Store database selected by `--state-dir` or
`AUTORESEARCH_HOME`, shared by CLI/TUI/web. Back up that database with the existing
run directories. New interface launches and `new` use these defaults when no explicit
`--config` is supplied. An explicit config seeds that interface's form and takes
precedence until settings are explicitly saved there. Existing runs keep their archived
configuration; use their dedicated budget/intervention controls to manage them.

Scriptable equivalents (no interactive input or execution):

```bash
uv run metis settings show
uv run metis settings import project.local.json
uv run metis settings set budget.usd '40'
uv run metis settings set provider.model '"your-served-model"'
uv run metis settings check
uv run metis setup --check
```

`settings set` accepts an existing dotted path and a JSON value; use import for arbitrary
nested provider maps. `show` prints private configuration for local use, not a sanitized
public export. `check` / `setup --check` return 2 while local prerequisites are incomplete.
`setup` without `--check` requires a terminal. The existing `init` command still writes
an example file without overwriting an existing file.


## Appearance and quiet navigation

Both consoles offer charcoal (dark) and cream (light), with the same semantic colours.
Use the Theme control or `metis theme cream` / `metis theme charcoal`. The preference
is shared through the selected private Store and applied on launch. It is separate from
research settings and never changes an existing run's configuration. Browser Commands
uses Ctrl+K (Command+K on macOS); Escape closes the menu.

Run `metis` for a short starting guide. Interactive `metis status` shows a concise
summary; `metis status --json` or `metis status RUN_ID --json` returns the complete
machine-readable record. Piped status output stays JSON automatically. `NO_COLOR`
and `TERM=dumb` suppress CLI colour. Execution shortcuts are inactive on TUI Home,
Settings, New run, Runs and Connections, where the selected run's controls are hidden.
