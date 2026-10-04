# Choosing experiment compute

In the browser, use **New research → Project → Execution → Review**. In the TUI,
use **Settings → Execution**, save, then create a new inquiry. `metis setup` asks
for the same backend and resource choices. Scripted setup can use:

```sh
metis settings set execution.backend '"slurm"'
metis settings set execution.cpus 8
metis settings set execution.memory_mb 16384
metis settings set execution.gpus 1
metis settings check
```

These choices apply to future runs. Explicit configuration files take precedence;
saved runs keep their configuration. Selecting compute does not start work.

| Backend | Execution location and isolation | Preparation and resources |
|---|---|---|
| Docker (default) | Container on the controller's Docker host; no workload network, read-only root, private writable experiment directory, protected read-only evaluator | Prepared dependency image; explicit read-only dataset mounts. CPU/memory limits and GPU access per command. |
| Local | Subprocess as the controller's OS user, with that user's permissions; not a sandbox | Installed runtime/dependencies; explicit `allow_local=true`. CPU/memory/GPU allocation settings are not enforced. |
| Slurm | Scheduler compute node; restricted environment but no added container isolation | Controller has scheduler tools; nodes have dependencies and shared workspace storage. CPU/memory/GPU requests per job, partition/account optional. |

Connections chooses the local or SSH controller independently. Local execution on
an SSH controller means the remote host, not the browser's computer. Docker dataset
mount mappings are not applied to local or Slurm; use paths accessible there.
No backend provisions a complete scientific environment merely by being selected.
PaperOrchestra has its own Docker/local execution settings under `paper_orchestra`;
the experiment selector does not switch manuscript execution.

## Scheduling and source isolation today

A research run has one active workflow worker and one pending formal experiment.
Candidate evaluation and seed repetitions execute serially within that run. Slurm
retains a pending job and polls it; choosing Slurm does not submit an experiment
batch concurrently. Separate runs can overlap; no controller-wide CPU/GPU quota or
resource admission queue coordinates them. Model panels are separate from experiment
scheduling. Per-job resource settings are not a total run or host allocation.

Each coding session has an original snapshot, editable working directory,
checkpoint, diffs and command receipts. Every formal attempt receives its own
`experiments/<id>` directory plus a pristine input snapshot, and runs the exported
source again under the protected measurement protocol. These are private filesystem
copies, not Git worktrees. Git metadata is excluded from admitted source. This
supports non-Git inputs and keeps generated code away from the user's working tree,
but copies can consume substantial storage. Failed attempts remain evidence.

See [coding](coding-harness.md), [execution](architecture.md#experiment-boundary)
and [reproducibility](reproducibility.md). Implementation: `engine.py` `_experiment`,
`coding.py` coding sessions, and `execution.py` `Executor`.

## ScientistTwo: checked 2026-10-01

The paper describes two ideas per round, one seed and one evolved candidate, with
subset evaluation, criticism, engineering and full evaluation; successful and
failed traces inform evolution. It does **not establish simultaneous execution or
Git worktree isolation**. [Sections 3.2–3.3 and Appendix A.2](https://arxiv.org/html/2609.19644v1#S3.SS2)

Most agents use Gemini 3.6 Flash; coding, ablation, rebuttal and draft enhancement
use Claude Code with Opus 4.8. The reported average cycle is 2–3 days and $3,765,
including tokens and virtual machines. The checked setup text does not specify
Docker, Slurm, GPU allocation, job scheduling or filesystem isolation.
[Appendix A.2](https://arxiv.org/html/2609.19644v1#A1.SS2),
[Section 4.3](https://arxiv.org/html/2609.19644v1#S4.SS3)

The [official account](https://github.com/scientist-two) listed only the
[website repository](https://github.com/scientist-two/scientist-two.github.io)
at inspection. No executable orchestration implementation was located there.
The HTML and official repository were inspected; the 26 MB PDF could not be fetched,
so image-only appendix artifacts were not inspected. This is a bounded source audit.
The [integrity description](https://scientist-two.github.io/#integrity) emphasizes
reproducible scripts, rerunning results and manuscript/code agreement; backend
selection alone does not establish those properties or scientific parity.

## What parallel execution would require

The current single pending-experiment state is a real limit. A bounded within-run
scheduler needs persisted job identities and per-attempt state, aggregate resource
admission, atomic budget reservations, independent cancellation/recovery, and a
barrier before evidence comparison or candidate promotion. Start with independent
seed repetitions or fixed ablation plans; candidate evolution has scientific
ordering dependencies. Reuse isolated snapshots unless measured copy cost justifies
a different storage mechanism. Git worktrees alone provide neither a scheduler nor
a security boundary. These are proposed Metis extensions, not claims about upstream.

For concrete comparisons with AI Scientist-v2, AIDE, coding-agent worktrees and
trial schedulers, see [related agentic execution patterns](agentic-execution-patterns.md).
