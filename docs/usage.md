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

### Add providers from presets

Several providers offer free tiers; Metis can use more than one at a time. In
**Settings → Available to Metis**, choose **＋ Add provider**, pick a provider, tick the
models to enable and paste that provider's key into **API key**. Metis fills in the
endpoint, model IDs, key variable and published prices, and shows each model's published
free-tier limits and the provider's data-use terms word for word. The key goes to the host
vault or the current server session, exactly as above; settings record only the variable
name (for example `GROQ_API_KEY`). Repeat for each provider. A loopback server (Ollama,
vLLM, LM Studio) needs no key: choose **Local compatible server** and enter its model ID.

In a terminal:

```bash
metis settings preset list                    # providers, models, limits, data use
metis settings preset show groq:openai/gpt-oss-120b
metis settings preset add google:gemini-3.8-flash   # prompts for the key (hidden)
metis settings preset add local:qwen3:8b --base-url http://127.0.0.1:11434/v1
```

Paid providers work the same way. They have no free tier, so add them with `--tier paid`:

```bash
metis settings preset add openai:gpt-6.1-sol --tier paid          # OPENAI_API_KEY
metis settings preset add anthropic:claude-opus-5-5 --tier paid   # ANTHROPIC_API_KEY
metis settings preset add deepseek:deepseek-flash --tier paid     # DEEPSEEK_API_KEY
metis settings preset add google:gemini-3.1-pro-preview --tier paid
```

Claude models use Metis's native Anthropic adapter. The manuscript writer cannot use them
yet; keep an OpenAI-compatible model for the writing roles. DeepSeek stores data in the
People's Republic of China; read its data-use note before sending private research.

Choose **Plan**: *Free tier* records the provider's published free limits; *Paid
plan* records none (paid limits depend on your account) and uses the paid context
window where published. Metis refuses requests above a model's recorded context
window or tokens-per-minute limit, so free figures (for example Groq's 8,000
tokens/minute) block large prompts; pick *Paid plan* or edit `limits` if your account
allows more. In the CLI add `--tier paid`.

`preset add` asks for the key only in an interactive terminal and saves it to the host
vault; use `--no-key` to add it later. `--scope global|workspace|project` targets
[inherited model settings](settings-inheritance.md). In the TUI the same picker sits in
**Settings → Model → Provider presets**. `metis settings check` (and `metis check --config FILE`)
lists every enabled model with *key present* or *key missing*, its published limits and
its data-use caveat, without contacting the provider. Free-tier numbers are what each
provider published on the check date; your account may differ. See
[provider presets](model-routing.md#provider-presets) for sources.

### Which model does each role use?

With several models available, Metis chooses one per agent role for each new run.
Critical roles (experiment design, coding, scientific judgments, review and integrity
audits) get the most capable eligible model by the provider's own description; routine
roles get the cheapest. Free tiers come first, and work is spread across free models
so that no single daily quota runs out early. A model is skipped for a role when the
estimated request would not fit its context window or tokens-per-minute limit, or when
it lacks JSON mode. This choice makes no model call. `metis settings check` (and
**Check setup**) shows the plan: the models used, the expected number of calls, the
expected charge, the list-price equivalent and, when published daily quotas bind, about
how many days the run needs.

When you press **Start**, one short `model_router` call may refine the plan. It
runs only when at least two models are available, sees model and role descriptions but
no research content, and may only choose among the models the plan already allowed. If
its answer breaks a rule or the call fails, Metis keeps the plan and records why. The
chosen routes are frozen for the run and shown in **AI system → Model plan**. To turn the
call off, or to keep free tiers that may use your content for training out of the plan:

```bash
metis settings set model_selection.router '"off"'
metis settings set model_selection.exclude_data_use_caveats true
```

`model_selection` is a run setting: unlike models and keys it is not inherited through
workspace/project model settings or SSH parent snapshots, so set it where runs are
created. All figures are estimates from configuration and published limits, not
measurements.
Details: [automatic model selection](model-routing.md#automatic-model-selection).

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

### Wait for provider quota (opt-in)

Free API tiers often return HTTP 429 when the per-minute or daily request quota is
used up. Gemini's free tier also returns HTTP 503 with error status `UNAVAILABLE`
("model is currently experiencing high demand") for long periods. By default a run then stops with a recorded error and waits for you to
choose Resume. To let Metis wait and continue by itself, enable **Limits · Wait for
provider quota** in `metis setup` or the terminal workspace settings, or set it
before creating a run:

```bash
uv run metis settings set quota_wait.enabled true
```

The `quota_wait` configuration section has these fields:

| Field | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Wait after HTTP 429 or a 503 `UNAVAILABLE` overload response instead of stopping. |
| `initial_seconds` | `60` | First wait. Each consecutive 429 doubles it. |
| `max_interval_seconds` | `3600` | Longest single wait. |
| `max_total_seconds` | `93600` | Total scheduled waiting (26 hours, enough for one daily reset) before the run stops as before. |

A run keeps the configuration it was created with, so enable the option before
creating the run. Behavior while it is enabled:

- Only HTTP 429 responses and HTTP 503 responses whose JSON error status is
  `UNAVAILABLE` (the provider's explicit overload signal) qualify, after the
  provider's own short retries and any model fallback. When fallback is available,
  every permitted model must be limited this way. Other server errors (500, 502,
  503 without that status, and so on), network failures, rejected credentials, billing
  errors (including a 429 whose error code or type is `insufficient_quota`) and
  invalid model output still stop the run for an explicit Resume.
- Metis separates short-window limits (requests or tokens per minute; an advertised
  delay of at most 60 s) from long-window quota exhaustion (a longer advertised delay,
  a Gemini `QuotaFailure` whose quota id names a daily window such as
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, or an OpenAI-style
  `x-ratelimit-remaining-*: 0` header whose reset is more than 60 s away). Short-window
  limits keep the provider's bounded in-request retries. An exhausted quota stops after
  one request: retrying before the reset cannot succeed and would spend the remaining
  daily requests. This classification applies with or without this option.
- An exhausted model is recorded in the run (`model_quota_exhausted` in Activity, with
  the quota id, limit and reset time) and skipped until its reset across stages and
  restarts; other permitted models are used meanwhile (see
  [model routing](model-routing.md)). Waiting starts only when every permitted model is
  exhausted or limited.
- When every permitted model is exhausted, the next attempt is scheduled at the
  earliest model reset, capped at `max_interval_seconds`. A capped wake-up before that
  reset sends no request; it schedules the remaining time. Otherwise the wait is the
  larger of the provider's advertised delay (`Retry-After`, or Gemini's `retryDelay`)
  and the doubling backoff, capped at `max_interval_seconds`. A daily quota without an
  advertised reset is retried after one hour.
- The first model call after a wait is a single-attempt probe: no in-request retries,
  and its cost reservation covers that one attempt. Later calls retry normally.
- Exhaustion records stay until their reset time. After rotating the key or changing
  the tier, run `uv run metis resume RUN_ID --clear-quota` to forget them and try again
  immediately.
- The run shows `Waiting for provider quota; next attempt at HH:MM` in `metis status`,
  the terminal workspace and the browser. No model call is made before that time.
  Activity records a `provider_quota_wait` event for every such response, with the model,
  reason, wait and next attempt time. Earlier attempts are never removed.
- Pause works while waiting. Resume keeps the scheduled time; it does not try early.
- A successful step resets the backoff. When the total limit would be exceeded, the
  run stops with the original error, as it does without this option.
- Model cost, call and duration limits still apply. Each retry after a wait is a new
  request attempt. Providers usually do not bill rejected 429 or overload requests, but on a paid
  tier a retry that succeeds is billed normally, and every attempt counts toward the
  run's call limit. The duration limit includes time spent waiting.
- A rejected attempt whose response reports no token usage is charged Metis's
  conservative estimate for that request, as every unreported call is. With non-zero
  configured prices, a long wait with many retries therefore uses part of the model
  cost limit (`budget.usd`) even if the provider bills nothing. Check usage before
  raising the limit.
- Something must keep running the research: the browser console, the terminal
  workspace or `metis run`. Closing them leaves the run waiting; Resume continues it.

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


### Research process and agent traces

Overview includes the archived workflow’s task graph, conditional paths and recorded
visits. Select a phase or task to inspect it; **Follow current work** returns to the
run’s current phase. **Recorded attempts** opens individual passages through a stage.
The Temple is a compact broad-phase summary, not a percentage or scientific verdict.
Skipped phases stay unvisited, and an ended run retains its last recorded phase.

**Agent traces** displays recorded stage visits, model calls, subordinate receipts and
experiment attempts on a shared timeline. Expand a visit and select a row for its
metadata, duration and model cost. **Show task in graph** returns to that checkpoint.
Failures and repeated visits remain visible. Execution completion is separate from
scientific acceptance. Graph and trace inspection never starts or resumes research.

Costs use configured model rates and exclude compute, storage and external fees.
Parent totals include subordinate calls; child rows explain that total and must not
be added again. Reservations are shown separately. Estimated charges are labelled;
records without unambiguous attribution remain in **Unattributed records**. Missing
timing or unpriced execution is **—**, not zero. Stage/run elapsed time includes
waiting and pauses; call duration uses recorded timestamps. Parallel calls overlap.
These views also work for older runs, but cannot reconstruct missing historical data.

### Stage reports

In Research, open **Stage reports** to read each attempted stage checkpoint. Select
an entry for its status, new observations, recorded decisions and explanations,
evidence records and next stage. Expand complete records for the original details.
Writing checkpoints include the manuscript SHA-256 and byte length; versioned files
remain under **Manuscript & files**. Failed and repeated attempts remain separate.
Waiting means work is pending, and execution status does not imply scientific approval.

Reports are deterministic and make no model calls. They are saved atomically with
new attempted checkpoints, apply configured secret redaction, and contain private
research material. Historical checkpoints are not reconstructed; use **Activity &
traces** for older runs. Reports also appear as `stage_report` events in CLI/TUI
inspection and private exports. Metadata-only exports omit their research content.

## Experiment compute choices

See [execution options](execution-options.md) for GUI/TUI/CLI selection, backend differences,
per-job resources, source snapshots and current serial within-run scheduling.

Stage reports are displayed as formatted Markdown, including headings, lists, tables,
links and code blocks. **Download Markdown** saves the same document as a `.md` file.
This also works for already-recorded stage reports. **Original report record** retains
the complete saved JSON. Formatting is deterministic and makes no model calls.
Embedded HTML is shown as text; embedded images are not fetched. Downloads remain
private research content and require deliberate review before sharing.
