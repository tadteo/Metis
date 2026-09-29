# Using AutoResearch

Choose the web console for visual project setup and artifact inspection, the TUI for an interactive terminal session, or CLI commands for scripting. They use the same private store and saved runs. Launching an interface does not start research.

For a project on an SSH host, use **Remote connections** in the web console, the
terminal console's **Remote** tab, or `autoresearch remote`. The [managed SSH guide](remote.md)
covers saved/new hosts, in-interface MFA, installation, reconnecting and cluster storage.

## Configure a live project in the web console

Start from the repository root:

```bash
uv sync --frozen --group dev
uv run autoresearch serve
```

Open <http://127.0.0.1:8765> and choose **Create live research**. Enter a title and objective, then configure:

| Input | What to supply |
|---|---|
| Source directory | The project directory on the machine running AutoResearch. This is not a browser file upload. |
| Baseline command | An argument array such as `["python3", "train.py"]`. Paths to project scripts are relative to the experiment workspace; shell pipelines are not supported. |
| Evaluator and protected files | An independent evaluator command and the source paths/globs that agents must not edit. The evaluator writes the configured measurements. |
| Metric and reference result | The primary metric, its maximize/minimize direction and the original full-benchmark reference value. Use advanced JSON for multiple metrics. |
| Provider | Model ID, compatible API base URL and the **name** of the environment variable containing its credential. Set the actual credential in the server's environment. |
| Execution | Docker, explicitly enabled local execution, or Slurm. Select an image containing the needed dependencies and configure dataset mounts when appropriate. |
| Budget | An explicit model-spend limit. Advanced configuration includes call, experiment and wall-clock limits. |

The advanced configuration editor/import covers additional settings, including seeds, full benchmark rules, multiple metrics, agent counts, model routing, Slurm settings and read-only dataset mounts. JSON commands must be arrays of separate arguments. A relative source path is resolved by the AutoResearch process, so an absolute path is less ambiguous when launching from another directory.

Source snapshots always exclude known credential filenames and private tool directories such as `.env`, `.ssh`, `.config` and `.codex`, including when `project.include` uses `*`. Setup checks use the same exclusions. Keep inclusion patterns minimal: filename rules cannot identify every secret embedded in ordinary source or prose.

Run readiness validation and resolve its errors before creating the run. Validation checks local configuration and available infrastructure without paid model calls. Warnings describe remaining uncertainty: a locally valid key or URL does not prove authentication, model availability or schema compatibility, and an installed image does not prove the benchmark's dependencies or evaluation protocol are correct.

Create the run, inspect its saved configuration, and then explicitly choose **Start** or **Step**. Creation records configuration and copies the selected source files; execution can use model credits and compute resources. Configuration is fixed for that run. To change the project, model routing or execution backend, create another run with revised configuration. Budget limits have a dedicated update action.

For an existing configuration:

```bash
uv run autoresearch serve --config project.local.json
```

This fills the form's defaults. It does not change previously created runs. `.env` files are not loaded automatically. See [reproducibility.md](reproducibility.md) for the full project protocol and execution requirements.

## Work in a terminal

Generate a configuration, edit it, and open the interactive TUI:

```bash
uv run autoresearch init project.local.json
uv run autoresearch tui --config project.local.json
```

To open a saved run directly:

```bash
uv run autoresearch tui --run RUN_ID
```

The TUI uses the same saved configuration and checkpoints as the web console and CLI. Selecting a run does not execute it. The sidebar lists saved runs. Its tabs show the research tree, experiments with metrics/logs/provenance, activity and saved agent traces, manuscript, intervention/budget controls, and new-run configuration. **Agents / costs** shows configured model routing, writer subcalls and recorded usage. **Artifacts** lists private artifact paths, hashes and reviews. **Fidelity / evaluation** shows implementation evidence and failed-attempt denominators; it does not treat demo output or review scores as measured scientific parity. **New run** accepts a title, objective and configuration file path, with separate setup-check, live-creation and demo actions. Edit that JSON file with your editor, or use the web console's setup form.

| Key | Action |
|---|---|
| Ctrl+N | Open new-run setup. |
| Ctrl+R | Start or resume the selected run. |
| Ctrl+S | Run one checkpoint step. |
| Ctrl+P | Request a pause at the next checkpoint. |
| Ctrl+Q or Ctrl+C | Request a pause, finish the active checkpoint and exit. |

Quitting during a model call or experiment can take time because the active step must finish. Inspect diagnostics before resuming a blocked or budget-exhausted run. The TUI uses Textual and needs an interactive terminal; it does not require a browser or curses.

For scripts, use the CLI:

```bash
uv run autoresearch check --config project.local.json
uv run autoresearch new --title 'Public benchmark study' \
  --objective 'Test a documented limitation under a fixed evaluation protocol.' \
  --config project.local.json
uv run autoresearch run RUN_ID --steps 1
uv run autoresearch status RUN_ID
uv run autoresearch fidelity
```

`check` prints readiness JSON and exits with code 0 when the checked setup is ready, or 2 when errors remain. It makes no paid model calls. `new` only creates the run. `run` executes it; `--steps 1` limits it to one engine step. A step may contain multiple model calls or one long experiment, so it is not a single-call spending limit.

## Inspect AI behavior

Run `autoresearch validate-specs` to validate agent, prompt and workflow contracts without model calls. Use `autoresearch system --role subset` for current instructions, `autoresearch system --mermaid` for the stage graph, or `autoresearch system --run RUN_ID` for the archived behavior bundle. Both consoles expose **AI system** views with recorded instructions, resolved routing, tools, validation and transition gates. These views do not substitute current prompts when an original bundle is unavailable. See [the AI system guide](ai-system.md) for extension and migration contracts.

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
uv run autoresearch pause RUN_ID
uv run autoresearch intervene RUN_ID --note 'Investigate the failed seed before continuing.'
uv run autoresearch budget RUN_ID --usd 50 --calls 3000
uv run autoresearch resume RUN_ID
uv run autoresearch export RUN_ID summary.json
```

Private state defaults to `~/.local/state/autoresearch`. Set `AUTORESEARCH_HOME`, or place `--state-dir DIRECTORY` before the command, to use another location. Both interfaces must point to the same state directory to show the same runs. Opening two interfaces is supported for inspection; a durable lease prevents concurrent advancement of a run.

## Try the offline demonstration

The web console has a separate **Offline demo** action. The CLI shortcut creates and immediately executes the complete fixture:

```bash
uv run autoresearch demo
```

The fixture uses scripted agents and real local synthetic regression subprocesses. Its review scores and hypotheses are synthetic; it does not make paid model calls or establish scientific capability. The [public regression project](../examples/README.md), in contrast, is a live-model integration example and can incur model charges.

## Resolve common startup problems

| Symptom | Next action |
|---|---|
| Missing credential | Set the configured environment variable in the shell/service that launches AutoResearch, then restart that interface. Do not paste the key into the JSON configuration. |
| Source or evaluator unavailable | Check paths on the execution host, the source inclusion patterns and protected-file matches. Project data is not automatically uploaded or copied. |
| Docker unavailable or image missing | Start Docker and prepare the configured image. Install research dependencies in that image before running; workload networking is disabled. |
| Local backend disabled | Use Docker, or explicitly opt in to local execution with the understanding that it has the host user's permissions. |
| Slurm tools or workspace unavailable | Launch on an appropriate submit host and ensure the private experiment workspace is shared with compute nodes. |
| Citation verification unresolved | Enable external literature retrieval or supply an independently validating literature adapter. Supplying references alone cannot verify their existence. |
| Budget exhausted | Inspect recorded usage, deliberately raise the necessary absolute limit, then resume. A longer wall-clock limit may also be needed after an extended pause. |

An accepted setup check means no checked local error was found. It is not a successful provider request, benchmark reproduction, external security audit or validation of ScientistTwo-equivalent research capability.
