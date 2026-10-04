# Coding workers and parallel experiments

Design proposal, 2026-10-01. Current behavior was traced at integration base
`66aab17`. This document changes no runtime behavior and claims no research parity.
See also [related systems](agentic-execution-patterns.md) and
[execution choices](execution-options.md).

## What exists today

Metis already has an iterative coding agent, implemented by
[`CodingSession`](../src/autoresearch/coding.py), rather than one-shot code generation.
The scientific [engine](../src/autoresearch/engine.py) invokes
[AgentRunner](../src/autoresearch/agents.py), whose
[specialist dispatcher](../src/autoresearch/specialists.py) selects the native coding
session for live coding roles unless an external role command overrides it.

The session copies source into a private workspace. The model receives the task,
budget, relevant state and bounded tool history, then emits one structured action:
inspect/search/read, edit/delete, execute a command, acquire a resource, inspect
history, finish or abort. The harness executes the action and returns observations,
including failures, for the next model call. It records checkpoints, source changes,
command receipts and model usage. The current provider uses JSON actions through
chat completions; native provider tool calling is not necessary for this loop to be
agentic. Default bounds include 64 actions and 24 commands.

Commands run through the configured [Executor](../src/autoresearch/execution.py):
local process, Docker container, or Slurm job. The model call runs in the controller;
the generated program runs on the selected compute backend. Docker provides the
configured container boundary; a local process or Slurm allocation is not itself a
sandbox. Slurm commands can yield and resume; local/Docker execution is synchronous.

Finish requires a successful command against the current workspace hash and a
validation criterion, then exports source edits and the execution command. That
check does not prove the command was a meaningful test. Coding checks are not formal
scientific evidence. The engine creates separate immutable experiment inputs, runs
seeds, validates protected evaluation results and obtains independent criticism.
Only accepted measured evidence can promote a candidate; failed attempts remain.

The concurrency limitation is concrete: RunState has one `active_output` and one
`pending_experiment`; the engine chooses the next seed from completed batch results.
AgentRunner's thread pool parallelizes ordinary panels, not the native coding
specialist that returns before that pool. A Store lease gives one coordinator
ownership of a run. Adding threads around the existing experiment method would race
shared state rather than provide independent experiment lifecycles.

## What to reuse from Claude Code

Claude Code's public repository does not provide an open-source core harness. Its
[license](https://raw.githubusercontent.com/anthropics/claude-code/main/LICENSE.md)
reserves rights and refers to commercial terms. The public
[Python Agent SDK wrapper](https://github.com/anthropics/claude-agent-sdk-python)
has an MIT component license but bundles the Claude Code executable; those are
different licensing and source-availability claims.

Anthropic documents a model-directed
[context, action and verification loop](https://code.claude.com/docs/en/how-claude-code-works).
Its official [Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)
is the supported integration route for that loop, tools and context management.
[Subagents](https://code.claude.com/docs/en/sub-agents) get separate contexts;
filesystem isolation requires an explicit worktree choice. A worktree prevents
editing collisions, but neither allocates a GPU nor provides a security boundary.
These statements use official documentation, not inspected proprietary core source.

## Proposed implementation

Keep one scientific coordinator. Give each coding task a stable ID, an immutable
view of its candidate revision and feedback, its own workspace and a bounded budget.
Workers produce source revisions and auditable results; they do not mutate shared
RunState or approve their own scientific evidence. Replace the current session
identity's dependence on global experiment history with explicit task identity, so
an unrelated parallel result does not change a worker's identity.

Add a small durable task dispatcher, reusing Store and Executor. Its public operations
are submit, inspect/collect and cancel. Persist task/attempt IDs, immutable input
hashes, requested resources, ownership leases, execution identities and receipts.
Keep the coordinator lease; worker completion writes job-specific records, which
the coordinator consumes. Reconcile interrupted submissions with backend receipts;
retain uncertain outcomes and make retries separate attempts rather than promising
exactly-once execution.

Inject command execution into CodingSession instead of constructing Executor inside
it. Route both pilot commands and measured jobs through resource admission. Maintain
separate limits for simultaneous coding sessions and CPU/GPU execution. Admission
must cover overlapping runs on the same managed host; a per-job GPU count is not an
exclusive device lease. For Slurm, rely on the scheduler for actual device allocation
and apply Metis's run-level admission and budgets as well. A coding session waiting
for compute must yield without occupying the compute capacity its child job needs.

Publish a source revision before measured submission: source hash, parent revision,
environment identity and execution parameters. Several seeds can reuse that revision
while writing separate output directories. Keep existing snapshot workspaces first;
add Git worktrees when branch-based editing or inspection is useful. Do not require a
new worktree per seed or mount writable user Git metadata into generated-code jobs.

Start with parallel independent seeds for one fixed candidate. Collect all required
results before comparison/promotion. Then add simultaneous coding tasks for separate
candidates, using explicit round inputs and comparison barriers. Launch order and
completion order must not silently change which evidence or feedback each candidate
receives. Preserve immutable protocols, reviewer independence and negative results.

The first code changes belong in task contracts and Store persistence, a dispatcher,
CodingSession's executor seam, and the engine's submission/collection path. Keep the
existing Executor backends. Sync execution can run in bounded owned workers; there is
no need to rewrite the whole application as async code. Extend UI status once actual
queued/running/waiting/completed task states exist.

## Optional Claude coding worker

Retain the existing provider-neutral coding worker. Add an official Claude Agent SDK
worker only as a second concrete implementation, using the same task inputs, revision
outputs and command/job dispatcher. An external role command can prototype this,
but its one-shot timeout and response envelope are not the final resumable lifecycle.

The integration needs more than launching `claude` with unrestricted tools. SDK shell
execution must not bypass Metis's execution policy or compute admission. Disable or
replace unrestricted execution with approved tools backed by the dispatcher, while
preserving the current provider-credential separation from generated commands.
SDK permissions alone are not an OS sandbox. Map resumable SDK sessions, tool traces
and nested model calls into existing provenance and
[aggregate accounting](accounting.md); reserve/enforce budgets before calls rather
than relying only on a final total cost. Validate these controls before enabling it.

Expose three independent choices: coding engine (native or available Claude SDK),
compute backend (Docker/local/Slurm), and concurrency/resource limits. Do not present
an unimplemented SDK worker as available. Worktree/snapshot policy describes source
isolation and is separate from all three.

## Acceptance evidence before implementation is called complete

Exercise simultaneous seeds with separate inputs/outputs, enforce resource and model
budgets across concurrent tasks, and verify that pilots cannot bypass admission.
Interrupt and resume queued/running jobs without silently duplicating submissions.
Check cancellation, unknown outcomes, out-of-order collection, missing-seed rejection,
protected evaluator integrity and candidate isolation. A future SDK worker must also
prove its tools cannot bypass those controls. Compare coding engines on fixed tasks
with recorded correctness, cost and failures before changing defaults. Software tests
alone do not establish autonomous research quality.
