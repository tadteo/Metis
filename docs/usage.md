# Inspect and run research

Install the locked environment with `uv sync --frozen --group dev --extra evaluation`.
Use `uv run autoresearch serve` for the web console or `uv run autoresearch tui --config project.local.json` for the terminal console. Both interfaces share the same private checkpoint store. Creating/selecting a project does not execute it. Start, Step and Resume explicitly execute research; Pause takes effect at a checkpoint. Decision feedback and stage overrides are recorded with their rationale and cannot force final completion.

The web console exposes stage history, model routing, per-call and subordinate writer usage, experiments, logs, reviews and downloadable binary/text artifacts. Its Fidelity & evaluation tab distinguishes reconstructed behavior from measured capability. The TUI exposes the same evidence, persisted paths, routing and intervention controls. Run `autoresearch fidelity` to validate/print the machine-readable matrix.

Live research needs a source project, registered benchmark protocol, protected evaluator, model credentials and an execution environment. Configure role providers and optional heterogeneous `role_panels` in the JSON editor. Grok 4.7 is the default general model. Set `laya.enabled=true` only with an available Laya `/v1/systemone` service; this uses typed advisory triage, not a chat-completions imitation. Configure `frontier_provider` for escalation. Substantive failures remain unresolved if escalation is unavailable.

Before manuscript stages, provision the pinned [official PaperOrchestra environment](paper-orchestra.md). Its native Google literature/image workflows require `GEMINI_API_KEY`; compatible writing/reflection/plotting text inherits configured Grok routing unless explicitly overridden. Missing prerequisites and upstream failures stop the writer without a local-writer fallback. Writer stage checkpoints, API caches and logs survive resume.

For actual public research-task evaluation, use the [evaluation guide](evaluation.md). It includes task preparation, protected baseline execution, complete live runs, paired variants and independently supplied quality ratings. The synthetic `demo` remains a plumbing test. API-dependent dimensions are reported as unmeasured when not run, and failures remain in the denominator.
