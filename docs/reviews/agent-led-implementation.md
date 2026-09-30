# Agent-led research implementation review

Base: f9e7d47. Branch: codex/agent-led-research.
Independent reviewer: review_agent_entry_implementation (read-only).

The reviewer checked scientific responsibilities, entry/input accounting, command
ownership, immutable measurement evidence, failure recovery, UI compatibility and
source provenance. This review does not certify research capability.

## Findings and resolutions

- Measurement checks now propagate command-only execution rather than requiring
  benchmark metrics from a diagnostic command.
- Raw SHA-256/length identities replace truncated or lossy text hashing for binary
  and large protected datasets and measurement artifacts.
- Malformed proposals, missing assets and unsupported citations enter bounded
  agent repair with retained proposal/audit evidence.
- Resource exports checkpoint intent before materialization, recover interruption,
  normalize transport failures, and accept identical inherited bytes.
- GPU resource settings reach Docker/Slurm commands and environment provenance.
- Intake enforces coding and total run deadlines while retaining discoveries.
- Scheduler job IDs bind to exact specification IDs across primary execution,
  protocol checks and instrumented measurement reproduction.
- Pre-acceptance baseline failure retains pristine implementation and earlier
  protocol/attempt versions, then independently inspects repairs. Accepted baselines
  cannot be unsealed by failed baseline re-entry.
- Auxiliary cancellation resolves the durable specification and writes its own
  cancellation receipt. Resume consumes it without resubmission or duplicate formal
  results; both pending scheduler fields clear.
- TUI readiness and creation share the same inquiry configuration.
- A real PDF fixture exposed unsupported macOS resource limits. The bounded worker
  now uses Linux address-space limits and macOS RSS supervision, with CPU/time bounds
  and worker termination/reaping on failure.

## Independent result

Approved feature integration after the accepted-baseline and cancellation repairs,
subject to required repository checks. The reviewer independently passed 25 focused
tests; its initially shared interpreter lacked the new PDF dependency. It then used
the worktree interpreter and independently passed both attachment extraction tests,
approving the platform fix. Whitespace checks passed.

GUI evidence covers charcoal/cream at desktop and 390px width, keyboard focus,
automatic folder creation and a saved idle inquiry with zero calls and zero cost.
TUI rendering was inspected at 80×24 and 120×40 in both themes, with scrollable
inputs and reachable creation controls. Public synthetic screenshots are retained
under [agent-entry evidence](../evidence/agent-entry/).

The paired live study remains unperformed. No paid provider, real GPU/Slurm cluster,
remote deployment or autonomous scientific-quality claim follows from these checks.

## Integration with concurrent reviewed work

Integrated committed main through f7ffe14, including coding-failure diagnostics and
specialist dispatch extraction. Kept both coding-harness documentation additions.
Intake now resolves pinned retrieval through SpecialistDispatcher.literature_for,
shared with manuscript review, instead of the removed AgentRunner helper. No scientific
routing/count change was introduced. Integration suites: 102 passed; browser 86 passed;
lint, types, format and specification checks passed. Unrelated dirty review and
implementation worktrees were inventoried and left untouched.
