# Inspecting and extending the AI system

The source of AI behavior is the packaged [specification bundle](../src/autoresearch/specs/),
not a collection of prompt strings in implementation code. Start with:

```bash
uv run autoresearch validate-specs
uv run autoresearch system --role subset
uv run autoresearch system --mermaid
uv run autoresearch system --run RUN_ID
```

These commands do not call models or execute research. The web console's **AI system**
view shows recorded agents, resolved instructions, routing, tools and transition gates.
The TUI's **AI system** tab shows the same recorded graph and agent contracts. Actual
calls, model identities, costs, failures and cache reuse remain in **Agents / cost**
or **Activity & traces**. A default routing preview does not replace a call receipt:
frontier escalation, panel membership and inherited coding roles resolve per call.

## One source for each decision

| Question | Authoritative artifact / implementation |
|---|---|
| Which agents exist? | [agents.json](../src/autoresearch/specs/agents.json): role, purpose, inputs, output schema, tool capabilities, handler, context/model policy, aggregation, validation, escalation and version |
| What are their instructions? | [prompts/](../src/autoresearch/specs/prompts/): separate Markdown role instructions, common guardrails, repair instructions and tool protocols |
| Which model is selected? | [policies/models.json](../src/autoresearch/specs/policies/models.json), saved provider/panel configuration and the pure [routing resolver](../src/autoresearch/routing.py) |
| Which tools are available? | [tools/tools.json](../src/autoresearch/specs/tools/tools.json), runtime allowlist and the strict coding/inspection action schemas; catalog permissions can restrict existing capabilities |
| How does the paper's loop run? | [scientist_two.json](../src/autoresearch/specs/workflows/scientist_two.json): 28 named stages, handlers, agents, inputs/outputs, limits, transitions, evidence guards, waits, unsuccessful outcomes and intervention policy |
| Where are scientific decisions implemented? | [research_stages/](../src/autoresearch/research_stages/): seeds, candidate experiments, manuscript/review and integrity handlers; the engine owns checkpoint/lease/budget/execution lifecycle |
| What memory does a model see? | [memory.py](../src/autoresearch/memory.py): complete scientific-history projection or frozen held-out evidence; failed and negative attempts remain in durable RunState, events and artifacts |
| What proves a run's identity? | [behavior.py](../src/autoresearch/behavior.py): immutable resolved bundle and drift checks; typed BehaviorIdentity/AgentRequest provenance in [contracts.py](../src/autoresearch/contracts.py) |
| Who enforces tool safety? | Coding/inspection action parsers, protected evaluator and Executor; supported shared primitives live in [runtime_support/](../src/autoresearch/runtime_support/) |
| Where are executable experiment programs? | [assets/programs/](../src/autoresearch/assets/programs/): standalone source files used by the demo, registered public evaluations and Slurm worker |
| How are quality and fidelity checked? | [agent contract fixtures](../tests/test_agent_specs.py), [workflow tests](../tests/test_workflow.py), [behavior tests](../tests/test_behavior.py), existing scientific/security suites and [capability evaluation](evaluation.md) |

Agent instructions describe scientific intent. Runtime code enforces permissions,
measurement provenance, spending limits and stage transitions. A prompt cannot grant
filesystem access, change the benchmark protocol or make a claim count as a measurement.
The workflow registry accepts only implemented handler names; JSON cannot import Python.
Role output validation runs before caching. Accepted experimental plans require an
identifier, question, intervention and expected evidence. Scientific rejection and
uncertainty do not require fabricated successful payloads. Typed shape validity still
does not establish scientific correctness.

## Specialist workflows

Live coding composes the original scientific role instruction (including its configured
override) with the separately versioned coding protocol. Its read/edit/execute/observe
loop is bounded by coding operational budgets; its finished implementation still goes
through protected measurement and an independent scientific critic. Inspection uses
read-only tools and a separate audit protocol. See [coding](coding-harness.md) and
[inspection](inspection.md) for checkpoint and tool-action contracts.

Live drafting and revision use the pinned official PaperOrchestra workflow:
outline → literature and optional plotting → section writing → reflection → strict
compilation. These agents use upstream native prompts, explicitly marked
`prompt_scope: upstream_native`; the local draft/revise text also serves the synthetic
demo and command-adapter contract. Their real prompt source is the pinned upstream
revision, never relabeled as a reconstructed system prompt. Each native call retains
request/model/usage provenance. See [PaperOrchestra](paper-orchestra.md).

ScholarPeer runs summary → initial literature → bounded expansion → parallel historian
and baseline scout → novelty and technical question/answer pairs → final synthesis.
Its attributed [Appendix G templates](../src/autoresearch/assets/scholarpeer/) remain
byte-verified. Runtime adaptation is an external local prompt. Subrole identifiers are
ordinary catalog agents with independent requests. Literature coverage and semantic
review checks remain enforced by the specialized adapter. See [ScholarPeer](scholarpeer.md).

## Changing behavior deliberately

For a new study, configure provider/model IDs, role providers, heterogeneous panels,
cheap/frontier/held-out models and budgets in the project JSON. `writing_writer`,
`writing_reflection` and `writing_plotting` are explicit upstream writer model slots.
They are not arbitrary new command-adapter or prompt-override role names.

To replace instructions, edit the referenced Markdown artifact and increment its agent
version; validate and run the relevant contract/scientific fixtures. Content hashes also
change, so forgetting a manual version bump cannot silently alter an existing run.
`prompt_overrides` remains available for private operator instructions and is archived.
For an independently versioned complete bundle, copy the packaged specs directory,
edit it, and set `specification_dir` to its location in private configuration. Missing
files, unknown roles, unsafe paths, unimplemented capabilities and invalid definitions
fail closed. The ScientistTwo workflow remains the platform's validated graph.

A new advisory/generator/critic role can use an existing trusted handler by adding its
definition and prompt. Invoke it through AgentRunner or reference it in a tested workflow
handler; model/prompt changes do not require core orchestration edits. New scientific
stages or new executable tools require a reviewed handler/action implementation and
behavioral tests. Adding a definition alone does not silently insert a new stage into
the published research process.

Python extension interfaces accept provider, executor, literature and stage-handler
adapters. Live custom adapters must implement `behavior_identity()` returning stable,
JSON-serializable configuration (including their actual model and tool policy, excluding
credentials and mutable observations). Built-in adapters pin validated configuration.
The runtime records this identity alongside implementation/source hashes; replacement
stage handlers must satisfy declared edges and evidence guards. Demo-only fixtures may
use a weaker source identity, explicitly labeled in the bundle. Custom transport clients
also require explicit identity. Preserve external adapter state through its audited
checkpoint contract and provide the same adapter on resume.

The default runner forwards Engine's injected literature adapter to ScholarPeer as
well as novelty and reference auditing. Each review restores the adapter's configured
cutoff and scopes its coverage to that review's searches while retaining earlier
history. Direct AgentRunner review calls also verify an injected adapter against the
pinned run. Custom runner factories must forward the same adapter declared through
`Engine(literature=...)`; their identity must describe any additional dependencies.
Native PaperOrchestra retrieval remains governed by its separately pinned upstream
workflow and provider configuration.

Command adapters pin the resolved executable and referenced script bytes. Script paths
must be absolute because workers execute in private directories. The bundle distinguishes
command adapters from official writer routing; actual models remain adapter-reported.
Pin the adapter's deployment dependencies separately: entrypoint hashes do not establish
its full dependency closure.

## Frozen runs and migrations

Creation archives `ai-behavior.json` privately: exact catalog source files, resolved
instructions (including overrides), agent/workflow definitions, output schemas,
configuration, routing previews and runtime source hashes. Each checkpoint links its
bundle digest. Calls distinguish agent version/definition, system prompt content,
actual request, route, actual model/provider, logical cache key, attempts and costs.
Budget edits have their own journal and do not invalidate scientific behavior.

Cached agent results retain the producing call's actual model/provider, call ID and
successful request provenance, including repairs or frontier routing. The logical
lookup request and configured model remain separate fields. Older caches that stored
only output remain usable, but their unavailable producing identity is explicitly
`legacy_unknown`; current configuration is never presented as an observed model.

Resume verifies the stored bundle and current executable/specification content before
making a model call or submitting an experiment. Restore the recorded installation,
specs and configured adapters after an upgrade, or start a new study; do not silently
continue an old run under new instructions. Recorded definitions remain inspectable even
when installed definitions differ. Deployment/container/library versions and external
adapter internals still need their existing execution/upstream manifests; an AI bundle
is not a claim of bitwise environment reproducibility.

Legacy checkpoints have no recoverable original prompt bundle. After reviewing a legacy
run and reconciling pending work, `autoresearch adopt-behavior RUN_ID` explicitly records
adoption of current behavior and marks original provenance unavailable. This command
cannot overwrite an already-pinned bundle and never starts execution. Restore the old
installation to reconcile an active legacy coding session before adoption.

Held-out evaluation freezes subsequent intervention on that run. Optimization model
views and official writer materials also exclude held-out review records. The complete
private evaluation history remains available to the operator. Do not manually feed
held-out judgments into a new study and still label its evaluation independent.

## Validation and limits

CI validates specs, Python typing/lint, all scientific/security regression tests, the
Node interface suite, public-content scanning, a synthetic end-to-end demo and an
installed-wheel run outside the source checkout. The wheel check verifies that prompts,
definitions, workflows and standalone programs ship with the application.

These checks establish software behavior. The [fidelity ledger](fidelity.md) continues
to distinguish exact/integrated/reconstructed/missing capabilities, intentional model
substitutions and measured evidence. Exact ScientistTwo orchestration prompts remain
unreleased in the audited sources. Live model quality, original benchmark replication,
review calibration and autonomous scientific capability remain unmeasured here.
