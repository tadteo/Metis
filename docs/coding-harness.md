# Iterative coding harness

Live baseline, subset, full, engineering, ablation and experimental rebuttal stages
use `autoresearch.coding.run_coding`. The agent can discover the entire admitted
repository, search file contents, read any portion of text files, apply multi-file
edits and exact replacements, delete/rename files, run tests or pilots, inspect
failures and iterate. Files need not have Python suffixes. Binary inspection and
other tools run through sandboxed commands. Exploration is paginated rather than
limited to a one-time source snapshot. Credentials, Git internals and symlinks are
excluded. `project.include` still controls what enters the private project copy.

The action protocol is typed and rejects unknown fields. There is one tool action
per model turn, returned in `AgentOutput.plans`. `CODING_PROMPT` lists its exact
schemas. Configured role-specific models are retained. Consecutive check or tool
failures trigger the configured frontier model at `escalation_after_failures`;
provider/token/cost records use the normal agent journal. If no frontier is
configured, the failure state remains visible and bounded by the explicit budget.

A successful test on the current content hash is required before `finish` can
export code and a reproducible command. This establishes engineering readiness,
not scientific improvement: the normal protected evaluator and independent stage
critic subsequently judge the formal experiment. Tests and pilots appear as
`coding_command` artifacts, separately from the formal experiment denominator.
The harness does not eagerly execute the final expensive benchmark and then run
it a second time simply to populate the engine's measurements.

## Persistence and safety

Each session keeps a private original snapshot, working directory, checkpoint,
per-command receipt, per-step diff and changed-file snapshots. Checkpoints survive
provider failures, preserve failed tests, and resume without repeating recorded
commands. An interrupted command without a durable completion receipt is marked
uncertain rather than blindly rerun. Slurm commands retain and poll scheduler job
identifiers. The UI journal exposes steps, command stdout/stderr, exit codes,
source and environment hashes, resource limits and artifact references.

All generated commands use `Executor`; no model text becomes shell syntax.
Docker is the default and uses disabled networking, resource limits, a read-only
container root and explicitly configured dataset mounts. Protected files are
mounted read-only both at their workspace locations and in the trusted evaluator
snapshot. Tool writes/deletions reject protected paths. Opt-in local and existing
Slurm execution are trusted compute modes rather than equivalent isolation;
post-command checks detect and reject protected-file modifications. Provider keys
are absent from workload environments. Full logs are bounded by the configured
`execution.max_log_bytes`, with truncation explicitly marked, so unlimited output
cannot exhaust the host. Source diffs and snapshots remain private artifacts.

The operational limits `coding.max_steps=64`, `max_commands=24`,
`wall_seconds=14400`, and `command_timeout=300` are configurable reconstruction
choices, not published ScientistTwo iteration counts. They do not replace the
outer paper-defined scientific engineering/refinement limits. Exhausting a coding
budget leaves the stage unresolved with diagnostics; it never creates a successful
control. Text edits default to a 2 MB per-file limit, and changed binary files must
be generated reproducibly by the exported command rather than encoded as text.

## Fidelity and validation

The [ScientistTwo paper §3.2 and Appendix A.2](https://arxiv.org/html/2609.19644v1)
uses an interactive coding backend for experiments, ablations and rebuttal. This
harness reconstructs that ability using the user-selected model providers; its
protocol, checkpoint format and operational budgets are engineering extensions.
No exact upstream prompts or Claude Code behavior are claimed. Table 8 reports
performance differences across coding backends, so replacement capability must be
measured rather than inferred from a matching tool list.

`tests/test_coding.py` executes a real multi-module Python test, observes its
failure, repairs code across files, reruns the protected test and checks exported
changes, complete failure retention, resumption, uncertainty handling, protected
file enforcement, large-file exploration and stale-check rejection. Executor tests
cover Docker limits and Slurm persistence. These establish software properties;
real-model coding success and research parity remain evaluation measurements.

Explicit dataset hashes use `project.dataset_manifest` entries such as
`"sha256:train_data.json": "<64 hex digits>"` for workspace files or
`"sha256:/data/public/train.csv": "<64 hex digits>"` for files in declared
read-only mounts. The executor streams and verifies every declared digest before
starting generated code. Traversal, special files, unavailable files and mismatches
fail execution. Provenance records `verified_sha256`, `file_manifest_verified` and
`unverified_manifest_entries`; descriptive metadata is not falsely marked verified.
This check certifies bytes at execution startup, not the scientific correctness of
a dataset or later changes made by an operator on the host.
