# Architecture

AutoResearch separates scientific decisions from model transport, experiment execution and durable storage. The [paper specification](paper-spec.md) defines the intended research behavior; [fidelity.md](fidelity.md) records where the implemented system is an approximation.

## Components

| Module | Responsibility and boundary |
|---|---|
| `contracts.py` | Strict Pydantic records for stages, hypotheses, agent requests/responses, file edits, experiment plans, measurements, usage and checkpoints. Unknown fields are rejected. |
| `config.py` | Versioned JSON configuration with validated limits, routing, project protocol, privacy and execution settings. Credentials are environment variable references. |
| `engine.py` | Advances one durable scientific stage at a time, records evidence and decisions, drives refinement loops, and resumes pending work. Every user interface uses this engine. |
| `writing.py`, `review.py` | Reconstructed multi-agent writer/reviewer subsystems: literature context, specialist decomposition, synthesis and criticism. They are not upstream packages. |
| `references.py` | Citation identifier and metadata re-retrieval checks with explicit unresolved issues. |
| `prompts.py` | Versioned reconstructed role instructions and output schema. Operator overrides are recorded through resolved requests. |
| `agents.py` | Independent agent panels, output validation/repair, explicit aggregation, model routing, optional frontier escalation, cache and accounting. |
| `providers.py` | `Provider.complete(AgentRequest) -> AgentResponse`; compatible chat-completions transport with bounded retries and conservative accounting when usage is unknown. |
| `literature.py` | Configurable scholarly retrieval adapters and literature evidence records with retrieval time and content hash. Supplied references extend the corpus but cannot independently verify themselves. |
| `execution.py` | `Executor.run`, `poll` and `cancel`; validated workspaces, commands and metrics for Docker, explicit local execution and Slurm. |
| `store.py` | Private SQLite run state, events, call reservations, usage, response cache, artifact manifests and worker leases. |
| `privacy.py` | Known-secret, home-path and user-pattern redaction. It does not make arbitrary research text anonymous. |
| `demo.py` | Deterministic synthetic agent behavior for offline workflow demonstrations. |
| `setup.py` | Local readiness checks for project configuration, credentials and execution tools; optional Docker runtime probes. It makes no model requests. |
| `source_policy.py` | Shared source exclusions for setup checks and initial snapshots, including credential filenames and private tool configuration directories. Include globs cannot override these exclusions. |
| `cli.py`, `tui.py`, `web.py`, `static/` | Scriptable commands, an interactive terminal application and a loopback web console; all operate on the same stored runs. |

## Checkpoint and ownership model

A `RunState` carries the current `Stage`, counters, hypotheses and their parents, selected/current candidates, experiments, evidence, review history, manuscript, accumulated memory and pending experiment information. The persisted `ResearchConfig` belongs to that run. Creating a new server with a different configuration does not silently reconfigure an existing run.

`Store.save` updates a checkpoint using an expected version and appends an event in the same SQLite transaction. Conflicting writers receive `ConflictError`. A run lease prevents two engine workers from advancing the same run. Same-host stale leases can be identified using process liveness; a foreign-host lease must not be assumed dead merely because the local process cannot see it. SQLite-backed state should stay on storage with SQLite-compatible locking, not an arbitrary shared network filesystem.

State is private, complete and resumable. Diagnostic events apply privacy controls; they are not the only copy of research content. Artifact records include SHA-256 and byte length. Raw database backups, cache entries and experiment directories must remain private even when trace detail is reduced.

Infrastructure failures are distinct from scientific decisions. An experiment can be pending, completed, failed, timed out or cancelled. A candidate can be scientifically rejected while its experiment completed successfully. The UI shows both levels rather than treating a process exit as a scientific success.

## Agent diversity and aggregation

`pipeline.agents_per_role` controls producer panels; `pipeline.critics` controls independent critics; `pipeline.parallelism` caps the panel worker pool. Panel members receive different review perspectives. Seed generation checks each new hypothesis for novelty before requesting the next; later generation sees the earlier scores and critiques. Producer panels can propose parallel additions as an explicit configurable extension. Evolution combines distinct hypotheses from prior successes and failures. Critics retain the most conservative verdict and the lowest score, aggregate feedback, and record disagreement. Disagreement or low confidence can invoke the explicitly configured `frontier_provider`. Without a frontier provider, an unresolved acceptance becomes a refinement request.

Live drafting decomposes the manuscript into outline, literature synthesis, parallel section drafts, figure planning, synthesis and bounded reflection/repair. Live review builds a structured summary and expanded literature context, runs historian and baseline-scout roles, performs novelty/technical question answering, then synthesizes the scored critique. The offline demo uses scripted equivalents and cannot validate the live subsystems.

The default general provider is used unless a role override applies. `cheap_provider` handles the currently designated high-volume roles, novelty and filtering; it must support the structured schema. These are routing decisions, not permission to omit critic, experiment or feedback stages. Exact routing precedence lives in `AgentRunner`; tests should accompany any change to it.

Caching is keyed by the run, semantic research state, request, prompt version, provider settings, panel index and adapter configuration. Administrative status/version timestamps do not invalidate a completed subcall; scientific feedback, counters and memory do. It reduces repeated work without treating a different experimental context as equivalent. Set `privacy.cache=false` when persistent response reuse is not appropriate. Cache entries are private research material.

Before a remote model call, the store reserves a conservative maximum cost. Completion settles observed usage; unreported billing is estimated conservatively. Configured prices are estimates, not a provider invoice, and external adapters must report their own usage accurately. Every external role command requires an explicit `role_command_max_cost_usd` reservation; its trusted wrapper must enforce that cap, passed as `AUTORESEARCH_MAX_COST_USD`. Unknown failures are charged conservatively and overruns stop subsequent work. Compute costs from Docker, Slurm, storage and retrieval services are separate from model-token accounting.

## Experiment boundary

An `ExperimentSpec` names an identifier, kind, workspace, argument vector, timeout, metrics filename, seed, proposed file edits and provenance metadata. There is no model-authored shell command string. The executor validates executable policy, workspace-relative paths and metric values before accepting a result. A trusted evaluator should remain outside model-editable files.

Docker is the default execution backend. It uses a read-only root filesystem with the experiment directory as the writable mount, no network, dropped capabilities, a non-root user and resource limits. Local execution requires `allow_local=true` and inherits the security limits of the operating-system user. Slurm uses validated scheduler arguments and a clean experiment environment; the worker must be able to access the shared workspace and configured runtime on the compute node.

The executor exposes `run(spec)`, `poll(spec, job_id)` and `cancel(job_id)`. A pending scheduler result retains the job identifier for resumption. The executor's receipt and specification hash bind recovered work to the expected experiment. Do not promise exactly-once remote submission unless the scheduler acceptance and durable receipt have both been reconciled after interruption.

## External role adapter protocol

`role_commands` maps a role name to an operator-owned argument vector. This is a privileged extension point for writers, reviewers or other specialized agents, not an installation of those upstream systems.

The adapter receives one UTF-8 JSON `AgentRequest` on standard input. Fields include `run_id`, `stage`, `role`, `system`, `prompt`, `schema_version`, `temperature` and `cache_key`. `prompt` is itself JSON text containing the checkpoint, project context and role-specific evidence. The adapter writes exactly one JSON `AgentResponse` to standard output, with `data`, `usage`, `model` and `provider`. `data` must validate as `AgentOutput`; diagnostics belong on standard error and must not contain secrets.

For a writer, `data.manuscript` contains the generated manuscript. A reviewer returns `summary`, `feedback`, `concerns`, `decision`, `confidence` and a 1–10 `score`. Schema validity is necessary but not sufficient: scientific claims must still be evidence-grounded. The implementation imposes a 600-second process timeout and an output size limit. Configuration currently forwards only a minimal environment and the role's configured provider-key variable; integrations needing additional services should manage explicit credentials in an audited wrapper rather than inherit the entire shell environment.

To integrate a new component: write the wrapper, pin its dependency revision, map its full input/output schema, record subordinate calls and costs, preserve private artifacts, and add a contract test plus a representative real evaluation. Merely setting a command name is not evidence of integration.

## Console boundary

The server binds to `127.0.0.1`, serves bundled static assets without external CDNs and authenticates data/mutation endpoints with a per-process token. Host/Origin checks and restrictive browser headers reduce cross-site access. This is a local single-user service, not a multi-tenant application or an internet authentication system.

The new-run form uses the server configuration as editable defaults. Its ordinary fields cover the project, baseline/evaluator, main metric and reference value, provider, execution backend and budget; advanced JSON editing/import preserves the full configuration surface. `GET /api/config` provides defaults, and `POST /api/preflight` checks a proposed configuration. Credentials remain environment variable references, rather than secret values entered into the form. Readiness results identify local errors and warnings; they do not assert remote model authentication, dependency completeness, literature availability or scientific correctness.

Validation and run creation make no model calls. Optional runtime probes inspect Docker availability and the configured image without running the research workload. A created run remains idle until an explicit execution action. Offline demonstration has a separate action and is visibly marked synthetic; it is not the default for a live project.

Each run has at most one in-process worker; the durable engine lease adds cross-process protection. Pause requests are checked at checkpoints. A human intervention records feedback and may select an earlier stage once the run is not executing. Explicit budget edits change absolute limits at a checkpoint without automatically resuming execution. Authenticated artifact downloads contain private research content. Export defaults to metadata; private export requires an explicit flag.

The Textual TUI opens the same private store and engine directly, without requiring the web server. `autoresearch tui --config CONFIG` supplies new-run defaults; `--run ID` selects a saved run. Opening it does not start a run. Its worker keeps input responsive during model calls and experiments. Exit requests a pause and waits for the active checkpoint rather than dropping its worker. The CLI is a separate command interface for automation and JSON output, rather than a substitute for the interactive terminal application. `autoresearch check --config CONFIG` exposes runtime preflight as JSON, with exit code 2 for incomplete setup. See [usage.md](usage.md) for operator controls.

## Replacing stages and policies

The Python engine accepts `provider`, `executor`, and `literature` implementations.
`runner_factory(store, config)` supplies a custom `AgentRunner` for alternative routing
or aggregation. `stage_handlers` maps a `Stage` to a callable taking
`(RunState, ResearchConfig, AgentRunner)`: mutate the state and next stage, and the
engine retains lease, budget, checkpoint and error handling. Replacements must preserve
the documented scientific transition contracts and receive their own fidelity tests.

Exact edited inputs are archived before each workload runs. Both later research stages and final reruns inherit these immutable inputs, not executed directories that can contain cached scores or trained checkpoints. Intentional warm starts belong in the registered source/data protocol. Model edits cannot replace protected evaluator paths. Before each experiment the engine
restores those paths from the original private source snapshot. Copying a workload to
the next experiment rejects symlinks and special files; these cannot be used to read
unrelated host paths. Docker mounts an independent evaluator snapshot read-only.
`execution.readonly_mounts` maps explicitly configured dataset directories to
`/data/<name>` in Docker. `project.dataset_manifest` records operator-declared checksums;
they are marked unverified until independently checked.
