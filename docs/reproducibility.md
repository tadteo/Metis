# Running and reproducing research

There are two separate claims to verify: that the software executes the intended control flow, and that a specific scientific result reproduces. Offline tests establish the first. A real research result requires actual model calls, trusted benchmark measurements and an independent artifact audit.

## Install and offline verification

Use Python 3.11+ and the committed dependency lock:

```bash
uv sync --frozen --group dev --extra evaluation
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync mypy src
uv run --no-sync pytest
uv run --no-sync python scripts/scan_secrets.py
uv run --no-sync metis demo
```

The demonstration is explicitly synthetic, deterministic and offline. It requires neither an API key nor a container/cluster. To inspect its recorded stages and artifacts:

```bash
uv run metis status
uv run metis serve
```

## Configure a real project

Generate an ignored local configuration with `uv run metis init project.local.json`. The complete supported schema is in `config.py` and `contracts.py`; unknown fields are rejected.

The [interface guide](usage.md) covers the editable web setup form, interactive TUI and CLI. `serve --config project.local.json` supplies editable defaults for new web runs; `tui --config project.local.json` opens the terminal interface with those defaults. Opening an interface, validating setup and creating a run do not start model calls. Start, Step, Resume and the CLI `run` command explicitly execute work. Existing runs retain their saved configuration.

Run `uv run metis check --config project.local.json` to inspect readiness as JSON before creating a live run. Exit code 2 means local setup errors remain. The check does not call a model or execute the benchmark, and warnings explicitly identify untested service access and dependencies.

| Configuration | What to record |
|---|---|
| `project.source_dir`, `project.include` | Explicit source checkout and minimal public/private files needed by the experiment. Exclude secrets, cached data and unrelated documents. |
| `project.baseline_argv` | A reproducible argument vector, such as `["python", "baseline.py"]`, for the reference implementation. No shell pipeline or shell expansion. |
| `project.metrics` | Every metric identifier and direction (`max` or `min`), ideally identifying dataset/split as well as metric. |
| `project.metric_units`, `project.analysis_artifacts` | Explicit units and protected evaluator JSON outputs used by the numerical/statistical claim ledger; see [claim integrity](claim-integrity.md). |
| `project.primary_metric`, `project.min_improvement` | Declared comparison policy. Multi-metric tradeoffs need explicit scientific interpretation. |
| `project.sota` | Operator-declared original full-benchmark reference values with source citations; subset reproduction must not replace them. These declarations require independent source verification. |
| `project.baseline_expected`, `project.reproduction_tolerance` | Expected reproduction values and acceptable numerical variation. |
| `project.specification` | Fixed datasets, splits, allowed training data, evaluation rules, resource restrictions and prohibited changes. |
| `project.evaluator_argv`, `project.protected_paths` | Trusted measurement entry point and files the model must not modify. The default live executor requires this protected evaluator. Code-generated self-reported metrics alone are insufficient evidence. A custom injected execution backend can implement an alternative trusted measurement boundary. |
| `project.seeds`, `project.experiment_timeout` | Recorded stochastic seeds and per-experiment time limit. |
| `pipeline` | Scientific limits, panel size, parallelism and escalation policy. The defaults and assumptions are in [paper-spec.md](paper-spec.md). |
| `budget` | USD model budget, call count, experiment count and wall time. These are operational limits, not scientific stopping evidence. |
| `privacy` | Diagnostic trace policy, response caching and additional redaction patterns. |

Each completed experiment must emit the configured metrics JSON with finite numeric values. Keep dataset checksums, source revision, dependency environment and evaluator version alongside the project's execution instructions. Stable preprocessing and split definitions are part of the experiment, not implementation details to retune after seeing results.

For an ATOM project or any unpublished research, keep its actual source/data/configuration outside the public repository. No ATOM data, cluster account or proprietary evaluator is bundled here.

## Models and cost

Export `XAI_API_KEY` before launching a default live run. The application does not load `.env` files automatically. The general provider uses the configured compatible `/chat/completions` endpoint and requests structured JSON. Update model identifiers and input/output rates to match the account and service in use; provider availability and prices can change.

For a compatible local model, configure `cheap_provider` with your loopback `base_url`, the exact served model name and a credential environment variable name. HTTP is permitted only on loopback; hosted services require HTTPS. A blank local credential is allowed when the local service does not require authentication. Set all local token rates to zero if the server is not billed per token, while accounting for its compute cost separately.

OpenRouter is configured with its compatible base URL and an `OPENROUTER_API_KEY` environment reference. Provider configuration is replaceable; the repository does not verify or download arbitrary model names. Laya uses the separate typed `/v1/systemone` advisory adapter, not `cheap_provider`; it cannot generate code or prose. See [Laya configuration](laya.md). The service remains operator-provided.

Recorded monetary totals use configured rates and observed or conservatively estimated token counts. They do not include cluster time, container compute, storage, external literature fees or unreported costs inside third-party wrappers. For a capability comparison, disclose those costs separately.

## Docker

Docker must be installed and its daemon available. Configure an image containing the project's dependencies and runtime. Pin a content digest for an actual reproducibility study; the convenience default `python:3.11-slim` is not an immutable scientific environment. Container experiments have no network access, so dependencies must already be in the prepared image. Explicit `execution.readonly_mounts` map absolute host dataset directories to container paths such as `/data/benchmark`; mount sources are validated and mounted read-only. Dataset mappings are not applied by the local or Slurm backend, which use paths already accessible on the execution host. Record dataset checksums under `project.dataset_manifest`. Entries named `sha256:relative/file` or `sha256:/data/mount/file` are verified against actual bytes by the executor before execution; descriptive entries remain explicitly unverified. This does not claim every dataset file is covered. The only writable mount should be the experiment workspace.

Do not give the experiment Docker socket access, host credentials or privileged mounts. Build and review an image separately from generated experimental code. Verify that the configured evaluator runs under the same restrictions and can access only the required evaluation inputs.

## Slurm and remote inspection

Set `execution.backend` to `slurm` and configure the partition/account in private configuration as needed. Run the orchestrator on a trusted cluster login/service host with `sbatch`, `squeue`, `sacct` and `scancel` available. Experiment workspace paths must refer to storage visible to the compute node; the trusted runner requires `python3` there. Provision dependencies according to cluster policy. Jobs use a restricted environment rather than inheriting model credentials.

Keep the SQLite orchestration database on storage with reliable local locking. If the database root is local to the orchestrator, arrange for its experiment workspace to be accessible to compute nodes through the deployment's storage layout. Do not assume that copying only the database makes an experiment resumable; preserve its corresponding source copies, artifacts and scheduler receipts.

`run` and `resume` continue from the saved stage and poll recorded jobs. Inspect scheduler state when recovering an interrupted submission; do not blindly resubmit a job that may still be running. A process timeout, a scheduler failure and a scientific rejection are different outcomes.

To inspect the web console remotely, start it on the remote host and use an SSH tunnel from the workstation, replacing the generic host alias:

```bash
ssh -N -L 8765:127.0.0.1:8765 research-host
```

Open `http://127.0.0.1:8765` locally. The console has no public bind mode and should not be exposed directly.

## Resumption, intervention and sharing

```bash
uv run metis run RUN_ID --steps 1
uv run metis pause RUN_ID
uv run metis status RUN_ID
# Optional: after the worker has paused, cancel a pending scheduler job.
uv run metis cancel-experiment RUN_ID
uv run metis intervene RUN_ID --note 'Explain this unresolved comparison before proceeding.'
uv run metis budget RUN_ID --usd 50 --calls 3000
uv run metis resume RUN_ID
uv run metis export RUN_ID summary.json
```

Budget values are explicit absolute limits, not increments; changing a limit does not resume a run automatically. Wait for the active checkpoint before intervention. Human input is part of provenance and changes the meaning of an autonomy claim. Use the same private state directory on subsequent invocations. Back up the database and its associated run directories together while workers are stopped or through a consistent SQLite backup procedure.

Metadata export is intended for a quick status exchange. A scientific reproduction package should additionally contain a deliberately reviewed, sanitized code snapshot, fixed evaluation protocol, environment lock, commands, dataset provenance, seed-level results, negative results, manuscripts and review history. Private export is not automatically safe to publish.

Report all attempted research tasks, including unsuccessful and budget-limited runs. Preserve the held-out reviewer/evaluator boundary and assess any model, retrieval, reviewer or stopping-rule changes as separate experimental factors. Do not call a synthetic demonstration a reproduction of ScientistTwo's reported performance.

## Live validation status

The automated suite executes real local synthetic experiments and exercises the Slurm
runner with a simulated scheduler. It validates Docker command construction and
mount/isolation configuration without requiring a Docker daemon in CI. A live xAI
research study, real Docker execution, real Slurm deployment and the paper's scientific
benchmark remain separate acceptance tests for a target deployment. No paid model
results or cluster performance claims are bundled.

The CLI returns exit code 2 for blocked, failed, stopped or budget-exhausted execution, so CI and external supervisors cannot mistake an incomplete run for success.

## Evidence matrix and continuation checks

After a component change, update `docs/fidelity.json` with published behavior, implementation files, existing commits, tests/evidence and a bounded remaining gap. Regenerate both reports and the package asset with `PYTHONPATH=src python scripts/update_fidelity_report.py`. The matrix test verifies commit ancestry using full Git history; shallow clones must fetch it. No matrix status alone authorizes a stronger scientific claim.

Writer recovery must confirm the prior local process group or named Docker container has exited before settling reservations or repairing an unterminated final journal record. A live or unverifiable worker blocks restart; unsupported legacy accounting also fails closed. Preserve the job directory and inspect the diagnostics instead of deleting journals or replaying unknown work. See [writer lifecycle](paper-orchestra.md).


## AI behavior identity

New runs archive their resolved agent/prompt/workflow/schema/configuration bundle and
runtime source hashes as a private `ai_behavior` artifact. Use `metis system
--run RUN_ID` to inspect it. Resume refuses changed behavior before work begins;
restore the recorded version or create a new run. Budget changes remain independently
journaled. Legacy runs require explicit `metis adopt-behavior RUN_ID` after
reconciling pending work; their original prompt provenance is marked unavailable.
See [the AI system guide](ai-system.md) for migration and extension constraints.

Model-call reservations, aggregate jobs, child receipts and legacy-ledger migration
are documented in [the accounting guide](accounting.md).

For Google Flash alongside the primary model, use **Settings → Model access → Add
Google Flash routing** or `metis settings profile google-flash`. Connect the Google
key separately, and save the edited settings for future runs. Optional Laya advice
has service controls in the same section. See [routing and its measurement limits](model-routing.md).

## Agent-established protocols

For agent entry, inspect `research_brief`, `research_protocol`, protocol inspection
and measurement-check artifacts alongside command receipts. Each formal result binds
to the protocol version and original input snapshot. Dataset manifests name actual
SHA-256 bytes. Measurement output hashes cover raw files, including binary predictions.
Separate scorers and protected data are restored from the sealed source; instrumented
measurements retain source identities and require a separately tracked pristine rerun
plus independent inspection.

Reference values must quote observed paper text in its published numerical scale and
identify the table or location. They are not inferred from the new subset reproduction.
The downstream subset/full critics and manuscript/statistical checks continue to use
the resolved facts under their existing rules. No scripted test certifies the
scientific meaning of an arbitrary new evaluator.

Failed baseline preparation may create a new inspected protocol version before any
baseline becomes eligible. All rejected proposals, checks and failed measurements are
retained. After baseline acceptance, a scientific rule change requires a new study,
so incompatible results cannot silently share comparison eligibility. Existing runs
with earlier behavior bundles require their recorded installation; this change does
not rewrite historical preparation costs or migrate old runs automatically.

## Long provider responses

The compatible transport defaults to SSE streaming (`provider.streaming=true`) and
3600 seconds of network inactivity (`provider.timeout_seconds`), with connection
establishment capped at 30 seconds. The read timeout is an inactivity limit, not a
three-minute deadline for the entire answer. Explicit saved timeout values remain
unchanged. Disable streaming for a compatible endpoint that does not support it;
ordinary JSON responses from endpoints that ignore streaming are also accepted.

Agent progress records report waiting, reasoning activity (when supplied), answer
character counts and response IDs. They do not expose reasoning text or imply a
percentage complete. The research page shows the last observed update inline;
Activity & traces retains the records. Accumulated answer text is recorded on normal
stream completion or a handled interruption, using the configured trace privacy and
redaction. Metadata-only traces omit answer text. Abrupt process termination can
lose in-memory partial text; this is not a crash-resumable remote request protocol.

Interrupted, malformed or truncated streams cannot become accepted scientific output.
After a stream has begun, transport does not automatically resend or change models:
remote completion is unknown, and a fresh request could duplicate paid work. Missing
final usage is conservatively estimated, including when an earlier cumulative usage
report exists. Completed usage uses the latest report once, never sums stream chunks.
The existing pre-response HTTP availability fallback remains bounded by the run budget.

Provider documentation checked 2026-10-01: [xAI streaming](https://docs.x.ai/developers/model-capabilities/text/streaming),
[xAI reasoning](https://docs.x.ai/developers/model-capabilities/text/reasoning), and
[Gemini compatibility](https://ai.google.dev/gemini-api/docs/openai).
xAI separately supports [deferred completions](https://docs.x.ai/developers/advanced-api-usage/deferred-chat-completions)
with one retrieval within 24 hours. Metis does not implement that protocol here.
Historical synchronous requests without response IDs cannot be recovered by turning
on streaming later. This runtime change requires a new explicitly linked continuation
for a pinned research run, retaining prior evidence and deducting earlier costs.


## Provider prefix caching

Orchestration sends the same canonical research context as stable reference messages,
ordered chunks of eight evidence records, then the current checkpoint/task/feedback.
The versioned common prompt defines lossless assembly, including evidence ordering
and unchanged JSON Pointer paths. Redaction and held-out filtering happen before
splitting. Independent critics receive no prior assistant answer or reasoning history.
New evidence can reuse complete prior chunks; edited reference content invalidates
the affected prefix. Canonical private traces retain the full JSON and `split_context`.
Non-orchestration callers retain their existing message format.

Direct xAI compatible calls use a hashed `x-grok-conv-id` stable for run, role, model
and system prompt. Other endpoints do not receive this header. Reuse is opportunistic:
server eviction, routing, changed prefixes and provider eligibility still affect hits.
Streaming does not disable prefix caching. This is separate from Metis's exact-response
cache; scientific outputs still require their full request identity.

`Usage.cached_input_tokens` records reported provider cache reads, or null when unknown.
Store usage exposes their sum and `cache_reported_input_tokens`, the input denominator
for calls with a known cache receipt. Missing historical receipts are excluded from
that denominator; they are not assumed misses. Retries with any unknown usage retain
an unknown combined cache count. Cache counts do not apply an invented discount:
monetary usage remains configured-rate accounting, not an exact provider invoice.
Reservations and unknown-usage estimates include the split-message framing.

Verified against [xAI cache matching](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/how-it-works)
and [routing guidance](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/maximizing-cache-hits)
on 2026-10-02. Offline tests establish unchanged payload content and reusable prefixes,
not a live hit rate or measured dollar savings. Existing pinned runs require an explicit
linked continuation to adopt the new runtime and prompt versions; no automatic restart.
