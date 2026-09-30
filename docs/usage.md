# Using Metis

Choose the web console for visual project setup and artifact inspection, the TUI for an interactive terminal session, or CLI commands for scripting. They use the same private store and saved runs. Launching an interface does not start research.

For a project on an SSH host, use the bottom-left **Local workspace** connection button in the web console, the
terminal console's **SSH connections** view, or `autoresearch remote`. The [managed SSH guide](remote.md)
covers saved/new hosts, in-interface MFA, installation, reconnecting and cluster storage.

## The temple on Home

A temple assembles stone by stone as a visual metaphor for inquiry. It is decorative,
not research progress. In the web console, drag the temple or focus it and use arrow
keys to rotate and tilt. The circular arrow in the corner rebuilds the temple. With
the temple focused, Space pauses/resumes and Home resets the view. Bricks drop straight
down at a steady pace; the
complete build takes about 23 seconds.
It rests after assembly and pauses when offscreen. Reduced-motion browser preferences
show the completed temple without a falling-block animation.

The terminal Home includes a simplified Unicode line drawing below the inquiry actions;
scroll or Tab to reach it on a small screen. With the temple focused, drag or use arrow
keys to turn/tilt, Space to pause, R to rebuild and Home to reset the view. These keys
apply only to the temple. `TEXTUAL_ANIMATIONS=none metis tui` shows it already assembled.
No temple interaction creates, starts or changes research.

## Begin with a question

Choose **New research** and describe what you want to investigate. Add associated
papers as PDF/text files or URL, DOI or arXiv identifiers if useful. The initial
research agent also discovers related literature. A project folder is optional:
choose an existing folder on the controller, create one, or leave it blank for a
managed workspace. New, partial and existing projects follow the same agent stage.

Creation saves the inquiry and copies admitted inputs without model calls. **Start**
begins research. The initial agent inspects available code and papers, identifies
the reference task, and asks for clarification only when evidence or access is
insufficient. Answer its question, then explicitly resume. Answers do not start work.
All agent calls, including intake and experiment preparation, use the same run's
model budget. Compute/storage costs are not included in this monetary cap.

The baseline coding agent retrieves or implements the reference method, chooses
commands, extracts published comparison values and builds measurement code. It runs
checks and submits the protocol to independent inspection. You do not have to supply
baseline commands, evaluator scripts or metric targets. Failed attempts and rejected
protocols remain in the record; bounded repairs consume the same budget. After a
baseline is accepted, changing its scientific comparison rules requires a new study.

Source acquisition uses configured HTTPS hosts and bounded downloads; repository
archives require pinned commits. Experiment networking remains disabled by default.
Pinned dependency wheels can be acquired and installed offline inside the experiment
environment. Docker/Slurm GPU requests use execution settings. Existing detached batch
launchers are not adopted as tracked experiments. Missing credentials, inaccessible
datasets or unavailable compute remain concrete blockers, not fabricated results.

This question-only entry is a Metis extension. Offline integration tests do not
establish autonomous research quality or parity with ScientistTwo. Previously saved
runs retain their behavior checks and need their recorded installation. Imported
configured studies remain available through CLI `--configured` or an explicit config.
Historical AI preparation receipts remain read-only at `GET /api/onboarding`;
separate prepare/generate/apply endpoints are retired.

## Configure a live project in the web console

Start from the repository root:

```bash
uv sync --frozen --group dev
uv run metis serve
```

Open <http://127.0.0.1:8765>. **Workspace settings** opens at **Model access**. Paste your provider key into **API key** and choose **Save API key**. The default stores it in the Metis server host's supported OS credential vault, where it survives a server restart. If the host vault is unavailable, explicitly choose **For this server session only**; that session key disappears when the server stops. A previous vault key cannot be checked or removed while vault access is unavailable, and may reappear when access returns. On a remote SSH console, the host is the remote machine. The key field clears after saving or closing setup. Metis does not put its value in settings, run configuration, browser storage or Metis-managed files. Expand **Model and API address** to change the default model ID or OpenAI-compatible URL. You can still use an environment variable: expand **Other ways to connect a key**, set the named variable on the server host and restart Metis. The setup check confirms that a key is available without displaying its value or contacting the model. A passing check does not establish that the credential or model actually works.

Choose **New research** to enter a question. Metis uses the beginning of the question
as the run name unless you expand **Name this run**. Model access carries over from
Workspace settings.

| Input | What to supply |
|---|---|
| Question | A free-text research objective. |
| Associated papers | Optional PDF/text attachments or paper identifiers. Extraction failures remain visible to the agent. |
| Project folder | Optional existing code/data on the controller. Metis copies admitted files and preserves originals. |
| Model budget | One model/API spending limit for intake and the complete pipeline. |
| Model and compute settings | Reusable provider/model routing and Docker, explicitly enabled local execution, or Slurm settings. |

The advanced configuration editor/import covers additional settings, including seeds, full benchmark rules, multiple metrics, agent counts, model routing, Slurm settings and read-only dataset mounts. JSON commands must be arrays of separate arguments. A relative source path is resolved by the Metis process, so an absolute path is less ambiguous when launching from another directory.

Project copies always exclude known credential filenames and private tool directories such as `.env`, `.ssh`, `.config` and `.codex`. Setup checks use the same exclusions. File selection cannot identify every secret embedded in ordinary source or prose; inspect the chosen folder before creating a live run.

Choose **Check setup** before creating the run. Agent entry checks inquiry prerequisites now and defers experiment readiness to the agents. Validation checks local configuration and available infrastructure without paid model calls. Warnings describe remaining uncertainty: a locally valid key or URL does not prove authentication, model availability or schema compatibility, and an installed image does not prove the benchmark's dependencies or evaluation protocol are correct.

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
| Missing credential | Open Model access and save the key, or set its named environment variable before launching Metis. Never paste it into Advanced JSON. |
| Source or evaluator unavailable | Check paths on the execution host, the source inclusion patterns and protected-file matches. Project data is not automatically uploaded or copied. |
| Docker unavailable or image missing | Start Docker, then choose Check setup. Metis can build from simple pinned Python requirements or fetch a configured image. Other dependency formats need an image prepared for the project; workload networking is disabled. |
| Local backend disabled | Use Docker, or explicitly opt in to local execution with the understanding that generated code has the host user's permissions and may read that user's credential vault. |
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
view retain advanced imported-study controls alongside Docker dataset directories, provider credentials by variable name,
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
research settings and never changes an existing run's configuration. In the browser,
the moon/sun button at the top right of the workspace switches themes. The TUI retains
its Theme control and Ctrl+T shortcut.

Run `metis` for a short starting guide. Interactive `metis status` shows a concise
summary; `metis status --json` or `metis status RUN_ID --json` returns the complete
machine-readable record. Piped status output stays JSON automatically. `NO_COLOR`
and `TERM=dumb` suppress CLI colour. Execution shortcuts are inactive on TUI Home,
Settings, New run, Runs and Connections, where the selected run's controls are hidden.


### Project folders in the browser

Choose **Choose folder…** to browse directories on the host running Metis, including
an SSH controller's filesystem. Use **Open location** for an absolute path (including
hidden directories), **Parent folder** to navigate, and **Use this folder** to select.
Cancellation keeps the current project. **Create new folder** allocates a unique private
folder and fills the path; Check setup also does this when the path is blank.
Creating a folder never replaces existing files or starts research. An empty folder
is a valid starting point: the agents develop the implementation and measurement
inside the pipeline after Start. The ordinary form has no experiment setup or separate
AI preparation budget.

CLI example (creates an idle inquiry):

```bash
uv run metis new --objective 'Investigate the limitations of the reference method' \
  --paper 'arxiv:2609.19644' --budget 25
```

Add `--project /path/to/project` to reuse existing source. In the terminal console,
**New research** offers the same objective, optional papers/folder and model budget.
