# Architecture

Metis separates scientific decisions from model transport, experiment execution and durable storage. The [research specification](paper-spec.md) records scientific contracts and their paper inspiration; [the evidence ledger](fidelity.md) tracks implementation, extensions and validation limits.

## AI specifications and runtime

The [AI system guide](ai-system.md) is the contributor entry point. The packaged
`specs/agents.json`, `specs/prompts/`, `specs/policies/models.json`, `specs/tools/tools.json`
and `specs/workflows/metis.json` govern agent identity/instructions, routing,
capabilities and scientific dispatch. `catalog.py` validates inert definitions;
`workflow.py` checks graph coverage, registered actions and actual transitions.
`research_stages/` contains the scientific handlers. `behavior.py` archives a resolved
bundle at creation and blocks continuation after behavior drift. CLI/TUI/web inspect
the same archived definitions; web stage labels/phases come from the workflow.

## Components

| Module | Responsibility and boundary |
|---|---|
| `contracts.py` | Strict Pydantic records for stages, hypotheses, agent requests/responses, file edits, experiment plans, measurements, usage and checkpoints. Unknown fields are rejected. |
| `config.py` | Versioned JSON configuration with validated limits, routing, project protocol, privacy and execution settings. Credentials are named references; values remain outside configuration. |
| `engine.py` | Advances one durable scientific stage at a time, records evidence and decisions, drives refinement loops, and resumes pending work. Every user interface uses this engine. |
| `writing.py`, `paper_orchestra*.py` | Pinned official PaperOrchestra agents with resumable stages, subordinate API accounting, isolated generated plots, safe compilation and immutable artifact bundles. |
| `review.py`, `assets/scholarpeer/` | Exact attributed Appendix G prompts with reconstructed retrieval/expansion/historian/scout/QA/synthesis orchestration. |
| `coding.py`, `inspection.py` | Iterative sandboxed coding and independent read-only source inspection with paginated access and durable tool observations. |
| `integrity.py`, `planned_statistics.py`, `evaluation.py`, `fidelity.py` | Literal claims and registered executed-statistic verification, real public-task evaluation and machine-checkable fidelity evidence. |
| `references.py` | Citation identifier and metadata re-retrieval checks with explicit unresolved issues. |
| `catalog.py`, `specs/`, `routing.py` | Validated agent/prompt/tool/model definitions, semantic output contracts and pure routing. `prompts.py` is a compatibility entry point with no instruction strings. |
| `workflow.py`, `research_stages/` | Executable stage graph, evidence guards and focused scientific handlers. |
| `behavior.py`, `memory.py` | Frozen behavior identity, drift verification and explicit model views that preserve negative evidence and isolate held-out judgments. |
| `runtime_support/`, `assets/programs/` | Supported secure filesystem/process primitives and independently inspectable executable programs. |
| `agents.py` | Independent agent panels, output validation/repair, explicit aggregation, model routing, optional frontier escalation, cache and accounting. |
| `specialists.py` | Specialist dispatch and orchestration for typed advice, source inspection, coding, official writing and review preparation; model subcalls use the runner’s accounted-call interface. |
| `providers.py` | `Provider.complete(AgentRequest) -> AgentResponse`; compatible chat-completions transport with bounded retries and conservative accounting when usage is unknown. |
| `literature.py` | Configurable scholarly retrieval adapters and literature evidence records with retrieval time and content hash. Supplied references extend the corpus but cannot independently verify themselves. |
| `execution.py` | `Executor.run`, `poll` and `cancel`; validated workspaces, commands and metrics for Docker, explicit local execution and Slurm. |
| `writer_accounting.py` | Durable subordinate-call intent, parent reservation reconciliation and cumulative writer caps; worker termination is confirmed before settlement. |
| `laya.py` | Validated non-generative HTTP advice with per-run private caching and real usage accounting; advice cannot replace an independent critic. |
| `store.py` | Private SQLite run state, events, call reservations, usage, response cache, artifact manifests and worker leases. |
| `privacy.py` | Known-secret, home-path and user-pattern redaction. It does not make arbitrary research text anonymous. |
| `demo.py` | Deterministic synthetic agent behavior for offline workflow demonstrations. |
| `setup.py` | Local readiness checks for project configuration, credentials and execution tools; optional Docker runtime probes and a shared ordered next-step projection. It makes no model requests. |
| `source_policy.py` | Shared source exclusions for setup checks and initial snapshots, including credential filenames and private tool configuration directories. Include globs cannot override these exclusions. |
| `cli.py`, `tui.py`, `web.py`, `static/` | Scriptable commands, an interactive terminal application and a loopback web console; all operate on the same stored runs. |
| `remote.py`, `ssh_auth.py`, `remote_runtime.py` | Managed OpenSSH profiles, transient interactive authentication, package provisioning, owned tunnels, and detached remote controller discovery/startup. Interfaces share one connection manager. |

## Agent-led entry and measurement

New GUI/TUI/CLI inquiries select `entry_mode=agent`; explicit imported configurations
retain `configured` semantics. `research_inputs.py` admits optional paper bytes and
identifiers without provider calls; the bounded PDF worker uses pinned pypdf 6.1.1
(BSD-3-Clause). `research_stages/intake.py` is a normal accounted workflow handler
with persisted coding-tool observations, discovered literature and a typed brief.
Unresolved intake pauses. A user answer creates a new input revision; it neither
mutates pinned configuration nor resumes spending.

`protocol.py` checks and independently inspects the baseline agent's proposed
measurement before sealing run-owned scientific artifacts. `resolved_config`
constructs an ephemeral view of these discovered facts after behavior verification.
The persisted configuration, models, scientific counters and comparison policy remain
pinned. Separate scorers use protected source; instrumented measurement additionally
requires original-source inspection and a pristine tracked reproduction.

Before a baseline is accepted, failed versions remain attached to their attempts and
bounded coding repairs can submit a new independently inspected protocol. After
acceptance, changing scientific rules requires a new study. Protocol source/hash
tampering blocks continuation. Raw byte identities cover binary and large assets.
Pending scheduler jobs bind to a specific execution specification, including checks
and independent reruns.

`acquisition.py` extends the coding tool loop with bounded, credential-free HTTPS
downloads and pinned repository archives. It exports content-addressed resources,
separately from text edits, into private execution snapshots. This is a local
implementation, with no claim of the unreleased ScientistTwo coding harness or
research-quality parity.

## Checkpoint and ownership model

A `RunState` carries the current `Stage`, counters, hypotheses and their parents, selected/current candidates, experiments, evidence, review history, manuscript, accumulated memory and pending experiment information. The persisted `ResearchConfig` belongs to that run. Creating a new server with a different configuration does not silently reconfigure an existing run.

`Store.save` updates a checkpoint using an expected version and appends an event in the same SQLite transaction. Conflicting writers receive `ConflictError`. A run lease prevents two engine workers from advancing the same run. Same-host stale leases can be identified using process liveness; a foreign-host lease must not be assumed dead merely because the local process cannot see it. SQLite-backed state should stay on storage with SQLite-compatible locking, not an arbitrary shared network filesystem.

State is private, complete and resumable. Diagnostic events apply privacy controls; they are not the only copy of research content. Artifact records include SHA-256 and byte length. Raw database backups, cache entries and experiment directories must remain private even when trace detail is reduced.

Managed SSH keeps the complete engine on the remote host. The laptop owns only its
connection and interface; closing the tunnel does not pause research. A private
descriptor and authenticated health check reconnect to the existing controller.
The descriptor's host and settings prevent silent replacement on another login node
or with changed storage. The Store accepts a separate database directory for local
SQLite storage while experiment workspaces remain shared. See [managed SSH](remote.md)
for filesystem, authentication and lifetime constraints.

Infrastructure failures are distinct from scientific decisions. An experiment can be pending, completed, failed, timed out or cancelled. A candidate can be scientifically rejected while its experiment completed successfully. The UI shows both levels rather than treating a process exit as a scientific success.

## Agent diversity and aggregation

`pipeline.agents_per_role` controls producer panels; `pipeline.critics` controls independent critics; `pipeline.parallelism` caps the panel worker pool. Panel members receive different review perspectives. Seed generation checks each new hypothesis for novelty before requesting the next; later generation sees the earlier scores and critiques. Producer panels can propose parallel additions as an explicit configurable extension. Evolution combines distinct hypotheses from prior successes and failures. Critics retain the most conservative verdict and the lowest score, aggregate feedback, and record disagreement. Disagreement or low confidence can invoke the explicitly configured `frontier_provider`. Without a frontier provider, an unresolved acceptance becomes a refinement request.

Live drafting invokes the pinned official outline, hybrid literature, section writing, content refinement and PaperBanana plotting agents. Generated plot Python runs separately without model credentials; final source is compiled under explicit no-shell-escape policy and captured with the PDF. Live review builds a structured summary and expanded literature context, runs historian and baseline-scout roles, performs novelty/technical question answering, then synthesizes the scored critique. The offline demo uses scripted equivalents and cannot validate the live subsystems.

The default general provider is used unless a role override applies. `cheap_provider` handles the currently designated high-volume roles, novelty and filtering; it must support the structured schema. These are routing decisions, not permission to omit critic, experiment or feedback stages. Exact routing precedence is declared in `specs/policies/models.json` and executed by `routing.resolve_route`; tests accompany changes.

Caching is keyed by the run, semantic research state, request, prompt version, provider settings, panel index and adapter configuration. Administrative status/version timestamps do not invalidate a completed subcall; scientific feedback, counters and memory do. It reduces repeated work without treating a different experimental context as equivalent. Set `privacy.cache=false` when persistent response reuse is not appropriate. Cache entries are private research material.

Before a remote model call, the store reserves a conservative maximum cost. Completion settles observed usage; unreported billing is estimated conservatively. Configured prices are estimates, not a provider invoice, and external adapters must report their own usage accurately. Every external role command requires an explicit `role_command_max_cost_usd` reservation; its trusted wrapper must enforce that cap, passed as `AUTORESEARCH_MAX_COST_USD`. Unknown failures are charged conservatively and overruns stop subsequent work. Compute costs from Docker, Slurm, storage and retrieval services are separate from model-token accounting.

## Experiment boundary

An `ExperimentSpec` names an identifier, kind, workspace, argument vector, timeout, metrics filename, seed, proposed file edits and provenance metadata. There is no model-authored shell command string. The executor validates executable policy, workspace-relative paths and metric values before accepting a result. A trusted evaluator should remain outside model-editable files.

Docker is the default execution backend. It uses a read-only root filesystem with the experiment directory as the writable mount, no network, dropped capabilities, a non-root user and resource limits. Local execution requires `allow_local=true` and inherits the security limits of the operating-system user. A local generated-code process may be able to access that user's OS vault even though Metis does not pass the key in its environment; use local execution only for a trusted workspace. Slurm uses validated scheduler arguments and a clean experiment environment; the worker must be able to access the shared workspace and configured runtime on the compute node.

The executor exposes `run(spec)`, `poll(spec, job_id)` and `cancel(job_id)`. A pending scheduler result retains the job identifier for resumption. The executor's receipt and specification hash bind recovered work to the expected experiment. Do not promise exactly-once remote submission unless the scheduler acceptance and durable receipt have both been reconciled after interruption.

## External role adapter protocol

`role_commands` maps a role name to an operator-owned argument vector. This is a privileged extension point for writers, reviewers or other specialized agents, not an installation of those upstream systems.

The adapter receives one UTF-8 JSON `AgentRequest` on standard input. Fields include `run_id`, `stage`, `role`, `system`, `prompt`, `schema_version`, `temperature` and `cache_key`. `prompt` is itself JSON text containing the checkpoint, project context and role-specific evidence. The adapter writes exactly one JSON `AgentResponse` to standard output, with `data`, `usage`, `model` and `provider`. `data` must validate as `AgentOutput`; diagnostics belong on standard error and must not contain secrets.

For a writer, `data.manuscript` contains the generated manuscript. A reviewer returns `summary`, `feedback`, `concerns`, `decision`, `confidence` and a venue-native `score` (ICLR 1–10; NeurIPS 1–6). Schema validity is necessary but not sufficient: scientific claims must still be evidence-grounded. The implementation imposes a 600-second process timeout and an output size limit. Configuration currently forwards only a minimal environment and the role's configured provider-key variable; integrations needing additional services should manage explicit credentials in an audited wrapper rather than inherit the entire shell environment.

To integrate a new component: write the wrapper, pin its dependency revision, map its full input/output schema, record subordinate calls and costs, preserve private artifacts, and add a contract test plus a representative real evaluation. Merely setting a command name is not evidence of integration.

## Console boundary

The server binds to `127.0.0.1`, serves bundled static assets without external CDNs and authenticates data/mutation endpoints with a per-process token. Host/Origin checks and restrictive browser headers reduce cross-site access. This is a local single-user service, not a multi-tenant application or an internet authentication system.

The new-run form uses the server configuration as editable defaults. Its ordinary fields cover the project, baseline/evaluator, main metric and reference value, provider, execution backend and budget; advanced JSON editing/import preserves the full configuration surface. `GET /api/config` provides defaults, and `POST /api/preflight` checks a proposed configuration. The authenticated `POST /api/credentials` route handles save, status and clear without returning key material. A separate password field sends the key only to that route. `credentials.py` resolves by name from process memory, a supported host OS vault, then the server environment. Metis never persists the value in configuration or run state. Trusted model workers receive only their configured credential; experiment subprocesses do not inherit it. Readiness results identify local errors and warnings; they do not assert remote model authentication, dependency completeness, literature availability or scientific correctness.

Validation and run creation make no model calls. Optional runtime probes inspect Docker availability and the configured image without running the research workload. A created run remains idle until an explicit execution action. Offline demonstration has a separate action and is visibly marked synthetic; it is not the default for a live project.

The readiness result retains every raw check, an ordered guidance projection and a
bounded preview of the actual selected project filenames for Review. The
browser automatically invokes bounded read-only project inspection when source-backed
command or protocol setup needs attention, then shows candidate file names without
accepting them as executable commands. Human-owned benchmark values, credentials and
host runtime changes remain explicit; paid AI preparation uses its separate preview
and receipt flow.
An authenticated browser setup recovery action can replace an unmatched include list
with an exact bounded eligible-file inventory. If a configured Docker image is missing,
it can fetch that image or build a local image from simple pinned Python requirements
using only a generated Dockerfile and the requirements manifest as build context.
Unsupported dependency manifests remain blocked; image availability does not verify
the benchmark or scientific protocol. The returned configuration is applied only to
the draft form and revalidated before run creation.

Each run has at most one in-process worker; the durable engine lease adds cross-process protection. Pause requests are checked at checkpoints. A human intervention records feedback and may select an earlier stage once the run is not executing. Explicit budget edits change absolute limits at a checkpoint without automatically resuming execution. Authenticated artifact downloads contain private research content. Export defaults to metadata; private export requires an explicit flag.

The Textual TUI opens the same private store and engine directly, without requiring the web server. `metis tui --config CONFIG` supplies new-run defaults; `--run ID` selects a saved run. Opening it does not start a run. Its worker keeps input responsive during model calls and experiments. Exit requests a pause and waits for the active checkpoint rather than dropping its worker. The CLI is a separate command interface for automation and JSON output, rather than a substitute for the interactive terminal application. `metis check --config CONFIG` exposes runtime preflight as JSON, with exit code 2 for incomplete setup. See [usage.md](usage.md) for operator controls.

## Replacing stages and policies

The Python engine accepts `provider`, `executor`, and `literature` implementations.
The default runner forwards the injected literature adapter to ScholarPeer; native
PaperOrchestra retrieval stays inside its independently pinned upstream workflow.
`runner_factory(store, config)` supplies a custom `AgentRunner` for alternative routing
or aggregation and must forward the adapter declared through `Engine(literature=...)`.
Pinned review calls reject missing or mismatched retrieval adapters. `stage_handlers` maps a `Stage` to a callable taking
`(RunState, ResearchConfig, AgentRunner)`: mutate the state and next stage, and the
engine retains lease, budget, checkpoint and error handling, and validates the resulting declared transition/evidence guards. Replacements must preserve
the documented scientific transition contracts and receive their own fidelity tests.

Exact edited inputs are archived before each workload runs. Both later research stages and final reruns inherit these immutable inputs, not executed directories that can contain cached scores or trained checkpoints. Intentional warm starts belong in the registered source/data protocol. Model edits cannot replace protected evaluator paths. Before each experiment the engine
restores those paths from the original private source snapshot. Copying a workload to
the next experiment rejects symlinks and special files; these cannot be used to read
unrelated host paths. Docker mounts an independent evaluator snapshot read-only.
`execution.readonly_mounts` maps explicitly configured dataset directories to
`/data/<name>` in Docker. `project.dataset_manifest` records operator-declared provenance. Entries of the form `sha256:relative/file` or `sha256:/data/mount/file` are verified by the executor against actual bytes before execution; descriptive entries remain explicitly unverified.

Model-call reservations, aggregate jobs, child receipts and legacy-ledger migration
are documented in [the accounting guide](accounting.md).

## Final evidence boundaries

Formal attempts enter the ledger before workspace preparation. A recovered receipt must match the registered specification; missing receipts remain uncertain rather than becoming replay permission. Pilot coding commands are recorded separately from formal seed experiments. Refinement attempts remain in the denominator even when the incumbent is kept.

Numeric manuscript claims bind literal spans, units, rounding and aggregation to immutable executed outputs. Statistical significance additionally requires a registered supported analysis, exact input fingerprints and recomputed arithmetic; see [claim integrity](claim-integrity.md) and [statistical analysis](statistical-analysis.md). Study validity still needs independent scientific judgment.

The source-inspection agent has read-only paginated tools and cannot execute commands or alter code. Final held-out review is retained in evaluation history but excluded from all subsequent optimizer and official-writer inputs, and evaluated runs cannot be reopened for optimization. This boundary is tested in `tests/test_agents.py` and `tests/test_writing.py`.

The fidelity matrix is canonical in `docs/fidelity.json`, validated against Git ancestry, current implementation/test paths and exact test nodes, then packaged for CLI/TUI/web inspection. Generated Markdown reports are checked for equality. It measures implementation evidence, not scientific parity.


## Workspace onboarding defaults

`settings.py` owns shared setup guidance, terminal field definitions and validated
private new-run defaults. The existing `settings` row retains non-model workspace defaults. `model_settings.py`
resolves validated model sections from per-user global defaults, workspace overrides
and canonical project overrides; managed SSH controllers receive a private parent
snapshot through the authenticated tunnel. `model_settings` rows store scope values
and revisions. Legacy workspace model choices remain overrides until reset. Saves use an immediate transaction and
compare an opaque safe-integer revision covering all relevant inherited layers; stale editors receive a conflict. Global then workspace transaction ordering serializes parent changes and scoped saves. Saved defaults use live
mode; demonstrations remain an explicit action. No settings operation edits a run or
starts an engine worker. The authenticated `/api/settings` endpoint shares these rules
with the terminal form and `setup` / `settings` CLI commands. `/api/config` supplies the
editable defaults, revision, guide and readiness; launch configs take precedence until
explicitly saved. Advanced JSON preserves options outside the common form fields.

## Advisory project onboarding

`onboarding.py` owns bounded read-only discovery and explicit project setup proposals.
The `project_setup` agent has a versioned prompt and no tools. A proposal's `structured`
AgentOutput validates against the strict Proposal schema; field allowlists prevent
provider, budget and permission changes. Source excerpts and their hashes, request,
provider settings, catalog hash, raw response, usage and failure are stored in the
private `setup_proposals` SQLite table independently of scientific runs. Atomic claim
prevents repeating a submitted request. Interrupted attempts remain uncertain.

The authenticated web routes separate inspect, prepare, generate and apply. Only
generate calls a provider, with retries disabled and a checked reservation. Apply
returns a validated configuration for the form, preserves unselected fields and
rechecks cited source excerpts. It neither saves defaults nor edits files. Draft
adapters are inert proposal text. Research creation and execution still use the
existing server-side readiness, budget, snapshot and evidence boundaries.

See [model settings inheritance](settings-inheritance.md) for scope identities, migration, CLI usage and SSH synchronization limits.


## Read-only execution presentation

`process_view.py` projects a consistent Store snapshot of checkpoints, events,
reservations and subordinate receipts for the authenticated `/api/runs/{id}/process`
endpoint. It does not advance research, read private artifact bodies or infer missing
model spans. Ledger charges are counted once; child receipts are explanatory.
Unambiguous identities link call and execution records, otherwise attribution stays
unknown. `static/process.js` renders that projection against the run’s archived
workflow. Scientific transitions and provider accounting remain owned by the engine
and Store. The existing activity/evidence inspectors retain full record access.
