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

# Choosing experiment compute

In the browser, use **New research → Project → Execution → Review**. In the TUI,
use **Settings → Execution**, save, then create a new inquiry. `metis setup` asks
for the same backend and resource choices. Scripted setup can use:

```sh
metis settings set execution.backend '"slurm"'
metis settings set execution.slurm_container '"apptainer"'
metis settings set execution.apptainer_image '"/proj/project/images/project.sif"'
metis settings set execution.cpus 8
metis settings set execution.memory_mb 16384
metis settings set execution.gpus 1
metis settings check
```

These choices apply to future runs. Explicit configuration files take precedence;
saved runs keep their configuration. Selecting compute does not start work.

| Backend | Execution location and isolation | Preparation and resources |
|---|---|---|
| Docker (default) | Container on the controller's Docker host; no workload network, read-only root, private writable experiment directory, protected read-only evaluator | Prepared dependency image (`execution.docker_image`); explicit read-only dataset mounts. CPU/memory limits and NVIDIA GPU count per command. |
| Podman | Same container boundary as Docker without a daemon. Rootless Podman maps your user ID into the container (`--userns keep-id`) | Same image field; use fully qualified names (`docker.io/library/python:3.11-slim`) if Podman's short-name policy rejects a short one. Rootless limits need cgroups v2 with `cpu`, `memory` and `pids` delegated; **Check setup** reports it and Metis refuses to run otherwise rather than record limits that were dropped. GPUs need NVIDIA CDI. On macOS, start `podman machine` first. |
| Apptainer | Container from a SIF image (`execution.apptainer_image`), contained filesystem, PID/IPC namespaces, clean environment, `--network none`, `--no-eval`; only the experiment directory and a private temporary area are writable | Linux host with Apptainer ≥ 1.1 or SingularityCE ≥ 3.10 (checked by **Check setup**). Prefer a local `.sif`, hashed once per controller process for provenance (slow for very large images); `docker://` references are resolved at run time. NVIDIA GPU via `--nv`. CPU/memory are not limited on a workstation. For Slurm, compute nodes need Apptainer at the same path as the controller and the image on shared storage. |
| Sandbox | Native process in the OS sandbox: macOS `sandbox-exec` (deny-by-default profile) or Linux bubblewrap. No network; writes only to the experiment and a private temporary directory; home folder, Metis state, other experiments, `/Volumes` or `/home`, `/run` and shared temporary directories hidden; protected files read-only | Your Python environment (`execution.environment_dir`, or `python3` on PATH). Native GPU, including Apple MPS. CPU and memory are not limited. Linux needs unprivileged user namespaces. Not a container or virtual machine. |
| Local | Subprocess as the controller's OS user, with that user's permissions; not a sandbox | Installed runtime/dependencies or `execution.environment_dir`; explicit `allow_local=true`. CPU/memory/GPU allocation settings are not enforced. |
| Slurm | Scheduler compute node. `slurm_container: none` uses the node's software and optional Python environment, without added isolation. `slurm_container: apptainer` runs each job's trusted runner inside the Apptainer image with the same binds as above | Controller has scheduler tools; nodes share workspace storage (and the image or environment path). CPU/memory/GPU requests per job, partition/account optional. The scheduler's `CUDA_VISIBLE_DEVICES` is forwarded into GPU jobs. |

`execution.environment_dir` names a venv, conda or uv environment prefix. Its `bin`
directory is searched first for the allowed executables, and `VIRTUAL_ENV` or
`CONDA_PREFIX` is set. The trusted runner works with Python 3.6.2 or newer, so cluster system
interpreters can run it. Activation scripts (for example conda `activate.d` hooks) and
environment modules are not run; use an environment that works when its `bin/python3`
is called directly. For Slurm, keep the environment on storage the compute nodes see.

Connections chooses the local or SSH controller independently. Local, sandbox and
container execution on an SSH controller means the remote host, not the browser's
computer. Dataset mounts appear at their `/data/<name>` target in Docker, Podman and
Apptainer; the sandbox exposes the source path read-only; local and Slurm without a
container use host paths. No backend provisions a complete scientific environment merely
by being selected. PaperOrchestra has its own Docker/local execution settings under
`paper_orchestra`; the experiment selector does not switch manuscript execution.

### Which backend to choose

- **Laptop or workstation with Docker or Podman:** keep Docker, or choose Podman for a
  daemonless rootless setup. Both isolate a separate root filesystem.
- **Mac that needs its GPU (MPS):** Docker Desktop and Podman machine run Linux
  containers in a virtual machine without Metal/MPS access. Choose **Sandbox** with
  the environment that has your dependencies.
- **Linux workstation without a container daemon:** Apptainer, or the bubblewrap sandbox.
- **Cluster (for example NSC Berzelius):** run the controller on the login node
  (Connections → SSH), choose **Slurm** with **Apptainer**, and keep the `.sif` image
  and experiment state on project storage (`/proj`), not the home quota. Berzelius
  supports Apptainer and does not support Docker; its Enroot/Pyxis integration was
  removed in January 2024.

### Native sandbox details

The macOS profile denies everything by default. It then allows process creation, reading
files outside the hidden locations (plus the metadata of directories and symlinks, so paths
resolve), writing the experiment and private temporary directories, POSIX semaphores,
shared memory named like PyTorch/multiprocessing/OpenMP segments, Unix sockets inside the
private directory (PyTorch's shared-memory manager), the Apple-silicon GPU user client and
three system services: user lookup, power assertions and the Metal shader compiler. Network
is denied; Keychain and LaunchServices were unreachable in testing, and Apple Events and
launchd job submission are not among the allowed services. Paths enter the profile only as
`sandbox-exec -D` parameters, and Metis calls `/usr/bin/sandbox-exec` by absolute path.
Child processes inherit the sandbox. `HOME` and `TMPDIR` point to a short private directory
under `/private/tmp` that is removed after the command.

Metis asks the selected interpreter once, outside the sandbox, for `sys.prefix` and
`sys.base_prefix`, and allows those installation directories read-only, so a venv's base
interpreter works. Other `sys.path` entries, such as an editable install of the project,
stay hidden: they would expose the original project folder. Install dependencies normally
(not editable) in the environment. Paths inside Metis state or the experiment's siblings are
never re-allowed, and a dataset directory inside Metis state is rejected.

### Protected evaluation

The workload and the protected evaluator never share a process environment:

- Containers (Docker, Podman, Apptainer, Slurm with Apptainer) and the Linux sandbox give
  the trusted runner its own PID namespace. After the workload, the runner ends every
  remaining workload process (and waits until none is alive), restores protected inputs
  from the snapshot, and starts the evaluator with a fresh `HOME` and `TMPDIR` and no Python
  user site. It acts only as the first process of its namespace (PID 1, or PID 2 under an
  init shim); Docker and Podman get `--init=false` so a configured init cannot change that.
  Otherwise it refuses to evaluate. Without a container init, orphaned zombie processes from
  the workload are not reaped until the workload phase ends; they count toward the 256-process
  limit. Apptainer must be allowed PID namespaces (`allow pid ns`); **Check setup** runs the
  image with Metis's flags on the controller host to confirm it (compute nodes could be
  configured differently).
- The macOS sandbox has no PID namespace. The workspace directory itself cannot be renamed
  or replaced from inside the sandbox, and its identity is recorded before the workload
  runs. The evaluator then runs in a second sandbox on a copy made through no-follow
  descriptors (APFS copy-on-write where possible), with protected inputs restored, a fresh
  `HOME` and `TMPDIR` and no user site. Copying counts against the experiment's time limit.
  Metrics come from that copy; after a successful evaluation the metrics and analysis
  outputs are copied into the workspace for inspection. Provenance `outputs_returned` is
  false when the workspace changed identity or an output file could not be copied (for
  example an optional analysis artifact that was not produced). A leftover process may still
  overwrite those workspace copies later; the recorded result does not change.
- Local and Slurm without a container restore protected inputs before evaluation but do not
  isolate the evaluator (`evaluator_isolated: false`).
- Run the evaluator as a script (`python3 evaluate.py`). With `-m` or `-c`, Python imports from
  the experiment directory; **Check setup** warns about it.

Provenance records `evaluator_isolation` as `pid_namespace`, `separate_sandbox_copy` or
`none`. Before this change a daemonized workload could overwrite the Docker evaluator's
`metrics.json` (reproduced 3/3); the runner now ends such processes first.

On Linux, bubblewrap binds the host root read-only, unshares all namespaces (including the
network and PID namespaces), drops capabilities, replaces `/home`, `/root`, `/run`, `/tmp`,
`/var/tmp`, `/mnt`, `/media`, `/srv`, the home directory and Metis state with empty memory
filesystems, and then binds back the experiment (writable), the private temporary directory,
the Python environment and import paths, the protected snapshot and datasets. Mount order
is significant: later binds sit on top of earlier memory filesystems. NVIDIA device nodes are
bound with `--dev-bind` when GPUs are requested. The Linux sandbox has argv tests but has
not yet been executed on a Linux host in this project.

Limits:

- System software and other readable host files stay readable; CPU and memory are not limited.
- macOS: background processes an experiment starts (for example with `setsid`) can keep
  running after the command, still sandboxed: no network, writes only to that experiment's
  directory. They cannot change the recorded measurement, but they can change the workspace
  afterwards and use CPU. Metis does not kill them, because no reliable way exists to tell
  them apart from other sandboxed system processes; stop them in Activity Monitor if needed.
  Hidden directories' and symlinks' existence and link targets can be checked (`stat`,
  `readlink`), but not their contents or listings.
- macOS: Apple marks the `sandbox-exec` interface deprecated, although it still ships and
  OpenAI Codex, Anthropic's sandbox runtime and Gemini CLI use it. Re-test after macOS
  upgrades. The GPU rule covers Apple-silicon Macs. Any same-user process, sandboxed or not,
  can read another process's arguments and environment through `sysctl`; keep provider keys
  in Model access (the OS vault, which the sandbox cannot reach) rather than in the
  environment that launches Metis. A Metis controller that itself runs inside another
  Seatbelt sandbox cannot start a nested one.
- Linux: needs unprivileged user namespaces. Ubuntu 24.04 restricts them through AppArmor
  by default, some hardened RHEL builds disable them, and `user.max_net_namespaces=0`
  prevents network isolation. **Check setup** probes bubblewrap and refuses when it fails.
- Environments: conda activation scripts (`etc/conda/activate.d`) and environment modules are
  not run. Most scientific packages do not need them; packages that do (for example GDAL data
  paths) need an environment that works when `bin/python3` is called directly.
- Use a container when those limits matter.

Sandbox sources: [sandbox-exec(1)](https://keith.github.io/xcode-man-pages/sandbox-exec.1.html),
[Codex Seatbelt policy](https://github.com/openai/codex/blob/9b738582b13c2cdbeff54af0afd04c50c3e7ba09/codex-rs/sandboxing/src/seatbelt_base_policy.sbpl),
[Anthropic sandbox runtime](https://github.com/anthropic-experimental/sandbox-runtime),
[Gemini CLI profile](https://github.com/google-gemini/gemini-cli/blob/main/packages/cli/src/utils/sandbox-macos-permissive-open.sb),
[Bazel Darwin sandbox (last matching rule wins)](https://github.com/bazelbuild/bazel/blob/master/src/main/java/com/google/devtools/build/lib/sandbox/DarwinSandboxedSpawnRunner.java),
[Metal rules for Seatbelt](https://github.com/todesking/cc-sandbox-gpu-mac),
[bubblewrap manual](https://github.com/containers/bubblewrap/blob/main/bwrap.xml),
[NVIDIA devices in bubblewrap](https://developer.nvidia.com/blog/improving-cuda-initialization-times-using-cgroups-in-certain-scenarios/),
[Ubuntu user-namespace restriction](https://discourse.ubuntu.com/t/understanding-apparmor-user-namespace-restriction/58007),
[Docker Desktop GPU support](https://docs.docker.com/desktop/features/gpu/),
[Python venv](https://docs.python.org/3/library/venv.html),
[conda environments](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html).

### Alternatives considered (checked 2026-10-08)

| Option | Decision |
|---|---|
| Enroot/Pyxis (NVIDIA) | Not implemented. Admin-installed Slurm plugin, network isolation only since Pyxis 0.24 (2026-05); removed on Berzelius. |
| Kubernetes Jobs | Deferred. Network policy needs a separate enforcing plugin; not a laptop or HPC target. |
| Cloud sandboxes (Modal and similar) | Deferred: paid service and data egress. |
| SkyPilot | Not implemented: orchestration without workload isolation; overlaps the Slurm backend. |
| Charliecloud | Not implemented: shares the host network namespace. |
| nerdctl/containerd, podman-hpc | Covered by Docker/Podman semantics; no separate runtime. |
| SSH execution host separate from the controller | Not implemented; Connections moves the whole controller instead. |

Sources: [Podman run](https://docs.podman.io/en/latest/markdown/podman-run.1.html),
[Podman user namespaces](https://github.com/podman-container-tools/podman/blob/main/docs/source/markdown/options/userns.container.md),
[rootless cgroup v2 delegation](https://rootlesscontaine.rs/getting-started/common/cgroup2/),
[Apptainer exec](https://apptainer.org/docs/user/latest/cli/apptainer_exec.html),
[Apptainer networking](https://apptainer.org/docs/user/latest/networking.html),
[Apptainer GPU](https://apptainer.org/docs/user/latest/gpu.html),
[Berzelius Apptainer](https://hpc.pages.naiss.se/user-documentation/berzelius-docs/software/apptainer/),
[Berzelius Pyxis/Enroot removal](https://lists.nsc.liu.se/mailman/public/berzelius-users/2023-December/000054.html),
[Pyxis](https://github.com/NVIDIA/pyxis), [Slurm containers](https://slurm.schedmd.com/containers.html),
[Charliecloud ch-run](https://charliecloud.io/latest/ch-run.html).

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
`coding.py` coding sessions, `execution.py` `Executor` and `isolation.py` runtime
argument builders.

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
