# Experiment runtimes beyond Docker

Base: `7c34a8d`.
Branch: `codex/execution-runtimes`, isolated worktree.

## Request and finding

Request (2026-10-08): run experiments "not only in Docker but also [on the] computer or other
alternatives"; research online first, implement every option that makes sense, it must also run
on a cluster, and the user must be able to configure it.

Before this task Metis offered Docker (default), Local (opt-in, unsandboxed) and Slurm. Gaps found
in the code:

- Local and Slurm resolve `python3` from the controller's `PATH` (`execution.py` `_run_sync`,
  `_submit` job script with `PATH=os.defpath`). Allowed executables must be bare names, so there is
  no way to run with the project's virtualenv/conda environment (for example PyTorch with Apple
  MPS) on a laptop or with a conda environment on cluster storage.
- The only isolated choice is Docker. Docker Desktop on macOS cannot expose the Apple GPU.
  Podman (daemonless/rootless) and Apptainer/Singularity (the HPC container runtime used on
  Slurm clusters such as NSC Berzelius) are not supported, and Slurm jobs run without any
  container isolation.
- Local has no isolation: generated code can use the network, write anywhere the user can, and
  reach the user's Keychain, where Metis stores provider keys (probe below).

## Boundary

Keep `execution.backend` as the single "where experiments run" choice and keep
`Executor.run/poll/cancel` unchanged for engine, coding and protocol callers. Add backends and
optional fields; existing configurations, saved runs and their serialized form remain unchanged
(new fields are omitted while unset).

- `podman`: Docker-equivalent isolation through the Podman CLI (rootless user-namespace mapping).
  Shares `execution.docker_image` (an OCI reference).
- `apptainer`: Apptainer/SingularityCE container on the controller host, from
  `execution.apptainer_image` (local SIF path or registry URI), contained environment, read-only
  protected/data binds, NVIDIA GPU via `--nv`.
- `sandbox`: native process with an OS sandbox: macOS Seatbelt (`sandbox-exec`, deny-by-default
  profile) or Linux bubblewrap. No network, writes only to the experiment directory and a private
  temporary directory, home/state/credential locations hidden, protected files read-only.
  Native GPU (Apple MPS on macOS).
- `local`: unchanged opt-in, plus the environment selection below.
- `slurm`: unchanged scheduler semantics plus `execution.slurm_container`
  (`none` | `apptainer`) to run each job inside the Apptainer image on the compute node.
- `execution.environment_dir`: optional absolute Python environment prefix (venv, conda or uv) for
  native runs (`local`, `sandbox`, Slurm without container). Its `bin` is searched first.

Out of scope, recorded with reasons in `docs/execution-options.md`: Enroot/Pyxis, Kubernetes,
cloud runners, SSH execution hosts separate from the controller, within-run parallel scheduling.

## Affected surfaces and journeys

Browser: New research / Settings → Execution: backend select, per-backend help, image/environment
fields, Slurm container choice, review summary. TUI and CLI (`metis setup`, `metis settings set`)
through shared `settings.FIELDS`. Readiness checks in `setup.preflight` per backend.
Documentation: execution options, architecture boundary, usage, README, security notes.

## Acceptance

- Each backend builds a validated argv without a shell; model text never becomes syntax in
  profiles, job scripts or bind specifications. Paths that the runtime cannot represent safely
  are rejected.
- Protected evaluator snapshot remains read-only and outside model edits for container and sandbox
  backends; provenance records backend, runtime tool, image identity, environment and whether the
  evaluator was isolated and datasets applied.
- Sandbox (macOS, live on this machine): experiment completes; network, writes outside the
  workspace, reading a secret in `$HOME`, Metis state and Keychain lookups are denied; a protected
  file cannot be modified. PyTorch MPS works under the profile (manual evidence; not in CI).
- Environment selection: Local/sandbox runs use the configured environment's interpreter; Slurm job
  script uses it on the compute node.
- Slurm + Apptainer: job script runs the trusted runner inside the image with the same binds.
- Setup checks name missing tools/images/environments with a next step for each backend.
- Settings round trip through browser, TUI and CLI; no research starts from setup.
- Focused tests, full CI command set, browser and TUI visual checks (light/dark, desktop/narrow,
  80×24 and 120×40), independent review under `docs/reviews/execution-runtimes.md`.

## Attempts and evidence

Probes on macOS 27.0 (Darwin 27.0.0), before implementation:

- `sandbox-exec` present. An `(allow default)` profile with targeted denies blocked network,
  writes outside the workspace and a denied subpath while a later `allow` re-opened a nested path
  (last matching rule wins). Children inherited the sandbox. `launchctl submit` from inside failed
  (rc 1) while the unsandboxed control succeeded.
- With `(allow default)` the Keychain was still reachable from inside (search ran normally), so the
  backend uses `(deny default)` with an explicit allowlist.
- PyTorch 2.10 MPS (user conda environment, read-only) computed a matrix product under the
  deny-default profile with `iokit-open` and a small `mach-lookup` allowlist. Spawn and fork
  multiprocessing pools worked; network was denied; `lsappinfo` could not reach LaunchServices.
  The first attempt failed because `/dev/null` was not writable. An OpenMP warning ("Can't set
  size of /tmp file") remained after allowing `ipc-posix-shm*`; libomp's registration file in
  the shared `/tmp` is denied and the computation still succeeded.
- A probe `open -g -R /tmp` from inside the sandbox returned 0 and may have revealed `/tmp` in a
  background Finder window; LaunchServices was otherwise unreachable (`lsappinfo` returned NULL).
- A multiprocessing probe written as `python -c` hung (spawn cannot import functions defined in
  `-c`); a test defect, rerun as a script file.

## Research (2026-10-08)

Two read-only research passes against primary sources (official docs, man pages and the
source of Podman, Apptainer, bubblewrap, Codex, Anthropic sandbox runtime, Gemini CLI and
Bazel) changed the design:

- Podman: `--gpus N` means device *index* N, so GPUs are requested as CDI devices
  `nvidia.com/gpu=0..N-1`; `--read-only` adds writable tmpfs mounts unless
  `--read-only-tmpfs=false`; `/tmp` needs `notmpcopyup`; `keep-id` is valid only rootless;
  rootless cgroup v1 silently drops limits, so Metis reads `podman info` and refuses unless
  cgroup v2 delegates cpu, memory and pids; image IDs are bare hex.
- Apptainer: `--network none` is the only unprivileged network mode (bare `--net` means
  bridge); `--no-eval` prevents shell evaluation; `--env` splits on commas and `--env-file`
  is shell-evaluated, so variables travel as `APPTAINERENV_*`; `--containall` drops Slurm's
  `CUDA_VISIBLE_DEVICES`, now forwarded by the job script; unprivileged `--cpus/--memory`
  need a systemd session, so limits come from Slurm. Berzelius supports Apptainer only and
  removed Enroot/Pyxis in January 2024.
- Seatbelt: last matching rule of the same operation granularity wins; parameters are safe
  against profile injection; Metal needs only `AGXDeviceUserClient` and
  `com.apple.MTLCompilerService`; PyTorch DataLoader workers need `torch_`/`psm_` shared
  memory and a Unix socket in a short `TMPDIR` (104-byte path limit). Same-user processes can
  read other processes' environment through `sysctl` (documented limitation).
- bubblewrap: mounts apply in argument order; `--dev-bind` for NVIDIA nodes; Ubuntu 24.04
  AppArmor and hardened RHEL may disable unprivileged user namespaces, so setup probes it.
- Rejected or deferred with reasons: Enroot/Pyxis, Kubernetes, cloud sandboxes, SkyPilot,
  Charliecloud, nerdctl and separate SSH execution hosts (`docs/execution-options.md`).

## Implementation and verification

- `isolation.py` builds Seatbelt profiles, bubblewrap, Apptainer argv and environment
  selection; `execution.py` dispatches per backend, records runtime/image/environment
  provenance and keeps Docker's flags (only `--name` moved) and client environment unchanged.
- Settings: `execution.backend` gains `podman`, `apptainer`, `sandbox`; new optional fields
  `apptainer_image`, `environment_dir`, `slurm_container` are omitted while unset (existing
  saved settings and run configurations serialize unchanged). Browser, TUI and CLI expose them.
- Readiness: per-backend checks (`podman-daemon`/`podman-image`, `apptainer`,
  `apptainer-image`, `environment`, bubblewrap user-namespace probe) with guidance steps.
- The onboarding prompt's Slurm capability text was corrected (GPU requests, environment
  prefix, Apptainer); `project_setup` 1.0.3 → 1.0.4, bundle 3.4.0 → 3.4.1.

Live evidence on this Mac (macOS 27.0, PyTorch 2.10/2.12 in user conda environments, used
read-only):

- Sandbox through `Executor` with a protected evaluator: completed; reading `~/.zshrc`,
  the Metis state database and a sibling experiment, writing outside the workspace, network
  and modifying the protected evaluator were all denied; the private `HOME` was writable;
  the private directory was removed.
- MPS training (forward, backward, SGD) with `DataLoader(num_workers=2)` under the final
  profile completed with home and network denied.
- Attempts preserved: the first default-interpreter run failed (`PermissionError` on the
  venv's `pyvenv.cfg`) because only the resolved base interpreter was readable; fixed by
  allowing both the venv and base prefixes. After narrowing metadata access to directories,
  `execvp` of `.venv/bin/python3` failed because uv's interpreter path crosses a symlinked
  directory under the hidden home; fixed by allowing symlink metadata. A first fake-venv test
  fixture wrote an invalid `pyvenv.cfg` and broke Python startup; replaced with a conda-style
  prefix. One full-suite run failed `test_review_limit_preserves_default_and_configurable_complete_rebuttal_cycles`
  with "AI behavior changed" because source was edited during the run; it passed alone and in
  the next full run.
- A generated Slurm job script was executed with `/bin/sh` (no scheduler): it forwarded
  `CUDA_VISIBLE_DEVICES=0,1` to the workload and contained no provider key.

Not executed here: Podman, Apptainer and bubblewrap are not installed on this Mac and no
Linux host or cluster was used. Their argv, job scripts and failure handling are covered by
tests with fake runtimes; live validation on a Linux workstation and on Berzelius remains
open. Docker behavior is unchanged and covered by the existing tests.

Checks: `ruff format --check`, `ruff check`, `mypy src` (90 modules), `metis validate-specs`,
browser tests (109 passed), public-file scanner, synthetic `metis demo`, full pytest
**1267 passed, 4 skipped**. Interface: browser at 1280×900 (charcoal) and 390×844 (cream)
for Docker, Podman, Sandbox and Slurm+Apptainer views, field visibility and narrow reflow;
TUI at 80×24 and 120×40 in cream and charcoal, including the open six-option backend list and
the focused Python environment field. No run was created or started.
