# Review: experiment runtimes beyond Docker

Base `7c34a8d`; reviewed commits `29eff66` (feature) and `c5784f9` (docs) on
`codex/execution-runtimes`. Reviewer: an independent agent with read-only access that ran
the focused suites and live macOS sandbox attack probes in a scratch directory.

Verdict of the first review: **blocking issues**. Resolutions are in the fix commit that
follows this record; the re-review is recorded below.

## Findings and resolutions

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| B1 | blocking | Sandbox: the workload planted `usercustomize.py` in the shared private `HOME`; the evaluator imported it and reported `{"score": 999}` instead of 0 (reproduced with a Python 3.11 conda environment). | The evaluator never shares the workload's environment: in a private PID namespace the runner gives it a fresh `HOME`/`TMPDIR` and `PYTHONNOUSERSITE=1`; the macOS sandbox runs it in a second sandbox with its own private directory. Live regression test `test_seatbelt_evaluator_resists_background_processes_and_user_site`. |
| B2 | blocking | macOS Seatbelt does not end a double-forked `setsid` daemon; it overwrote `metrics.json` after the evaluator (`{"score": 888}`). | macOS evaluates a clone of the workspace in a second sandbox that leftover workload processes cannot write; metrics come from the clone. While verifying, the same attack was reproduced against the **existing Docker backend** on `main` (3/3, `{"score": 777}`); the runner now ends all other processes in its PID namespace before evaluating (fails closed outside one). Opt-in live test `test_docker_ends_background_workload_before_evaluation` passed with a local image. |
| I1 | important | Nested protected file swapped by renaming its parent directory (Seatbelt literal rule). | Seatbelt denies writes to protected files and their parent directories; the runner and the macOS evaluation copy restore every protected input from the snapshot before evaluation (all backends). Test `test_protected_inputs_are_restored_before_the_evaluator`; reviewer probe `protected_dir_rename_write` now denied. |
| I2 | important | Probing `sys.path` re-allowed an editable project install, exposing the original project folder. | Only `sys.prefix`/`sys.base_prefix` are re-allowed (`python_prefixes`); documented that editable installs outside the environment stay hidden. |
| I3 | important | A `--db-dir` outside home and state was not hidden. | Every `Store` registers its state and database directories with the sandbox (`register_private_root`). Test `test_store_directories_are_hidden_from_native_sandboxes`. |
| I4 | important | Check setup did not detect rootless Podman limits the executor refuses; no readiness tests for the new backends. | Shared `podman_mode`/`podman_limits_problem`; `podman-limits` check and guidance. New tests for Podman limits, Apptainer version/image, Python environment and sandbox credentials. |
| I5 | important | The runner crashed on Python < 3.10 (`X | None` in a signature, `is_relative_to`, `missing_ok`). | Runner is Python 3.6-compatible (cluster system interpreters such as RHEL 8). AST test plus compile check with the macOS system Python 3.9. |
| I6 | important | Seatbelt cannot stop reading other processes' environment (`KERN_PROCARGS2`). | Already documented; added the `sandbox-credentials` readiness warning when a provider key comes from the environment on macOS. |
| M1 | minor | Local `PATH` deduplication changed the environment hash. | Original concatenation restored when no environment is configured. |
| M2 | minor | `mount_access` changes Docker's provenance shape. | Recorded in the plan; the environment hash is unchanged. |
| M3 | minor | Unused bubblewrap dataset binds. | Removed. |
| M4 | minor | Directory/symlink metadata in hidden locations is visible. | Documented in the limits. |
| M5 | minor | Datasets inside state could be re-allowed. | Rejected with an error. |
| M6 | minor | Slurm+Apptainer needs the same tool path on nodes; SIF hashing cost. | Documented. |
| M7 | minor | Podman short-name policy. | Documented fully qualified image names. |
| M8 | minor | Apptainer version not checked. | Check setup requires Apptainer ≥ 1.1 or SingularityCE ≥ 3.10. |
| M9 | minor | Copy without a next step; Apptainer help omitted the writable temporary area. | Fixed. |
| N1 | note | bubblewrap never executed on Linux. | Remains open; stated in the plan, docs and fidelity gap. |
| N2 | note | Onboarding may suggest the sandbox. | Accepted: suggestions are selected by the user. |

## Verified by the reviewer

Seatbelt parameters resist profile injection; `/usr/bin/sandbox-exec` by absolute path;
reads of home, firmlinked home paths, state, siblings and outside files denied; TCP, UDP and
the Docker socket denied; LaunchServices, security, pasteboard, TCC, WindowServer and DNS
services unreachable; Docker flags and client environment unchanged except `--name`
position; Podman CDI devices, `keep-id` only rootless, `--read-only-tmpfs=false`,
`notmpcopyup`, fail-closed limits; Apptainer argv, `--no-eval`, `--network none`, `:ro`
binds and separator rejection; Slurm resume/poll/cancel unchanged; settings omission and
round trips; browser field visibility and TUI fields. Reviewer runs: focused Python suites
145 passed; `node --test tests/*_ui.mjs` 109 passed; Ruff and mypy clean.

## Re-review of `743bfe0` and resolutions

A second independent review (same safety rules, plus: never signal processes it did not
start) confirmed B1, B2 (Docker and macOS), I1–I5, M1 and M5 live, and found:

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| R1 | blocking | macOS: a leftover workload process could rename its workspace root and put a symlink to a hidden directory in its place; the trusted `cp`/`copytree` then copied that directory, and the protected evaluator ran on it. A regular-file/symlink swap race was also observed in about 40% of copies. `_return_outputs` copied artifacts even after a failed evaluation; the fallback copy was unbounded. | The Seatbelt profile write-denies the workspace directory itself (rename and replacement denied; creating files inside stays allowed, tested live). The workspace's device/inode is recorded before the workload runs and re-checked; the copy walks no-follow descriptors, recreates links without following them, clones regular files with `fclonefileat` or streams them, and counts against the experiment's time limit. Outputs return only after a completed evaluation and only while the workspace identity is unchanged. The reviewer's `probe_g` now shows `rename_root` denied and the evaluator never sees the hidden marker. Tests `test_trusted_copy_never_follows_workspace_links`, `test_seatbelt_workspace_cannot_be_renamed_but_stays_writable`. |
| R2 | important | The `pid <= 2` guard rejects Docker/Podman with a configured init, and Apptainer sites without PID namespaces. | Docker/Podman get `--init=false`. The guard is "PID 1, or PID 2 under a PID-1 parent". The reviewer suggested `NSpid`; the live Docker test showed a fresh `/proc` reports a single `NSpid` entry, so that signal was rejected. Check setup now runs the Apptainer image with Metis's flags and reports whether the runner would be the first process of its namespace (`apptainer-isolation`). |
| R3 | minor | After `kill(-1)` the runner waited only for its own children and continued after 5 s; a daemon holding the pipes delayed evaluation by up to 10 s. | The runner reaps children and polls `/proc` until only the namespace init and itself remain (zombies ignored), failing closed after 10 s; leftover processes are ended before the log threads are joined. |
| R4 | minor | Copy time not subtracted; fallback mode not 0700. | Copy time counts against the deadline; the private copy keeps its 0700 directory. |
| R5 | minor | `typing.NoReturn` needs Python 3.6.2; AST test covered only positional arguments; the refusal test ran the real runner with `kill(-1)` reachable. | Docs say 3.6.2; AST test covers all argument kinds; refusal tests run in-process with `os.kill` replaced. |
| R6 | note (pre-existing) | `-m`/`-c` evaluators put the workload-writable directory on `sys.path`. | Documented; Check setup warns (`evaluator-path`). |

## Verification of `63eb25f` and final resolutions

A third independent pass (same safety rules) verified R1–R6 live, including a symlink/directory
swap race (~7k swaps per run, 6 runs plus control: no hidden byte reached the evaluation
copy), hard links, `clonefile` and `/.vol` access, 50 MB files, PyTorch DataLoader workers,
the time limit and the Docker daemon attack. **No blocking issue remained.** Findings fixed
afterwards:

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| V1 | important (pre-existing) | macOS `killpg` returns EPERM when only zombies remain; `_terminate` turned finished multiprocessing workloads into "could not be started" (local 2/3, sandbox 1/3). | `_terminate` and the runner treat `PermissionError` like `ProcessLookupError`. Test `test_zombie_only_process_groups_do_not_fail_a_finished_command`. |
| V2 | important | The workspace `file-write*` literal also blocked `touch .`, `tar -x`, `rsync -a` and `copytree` into the workspace. | Only `file-write-create` and `file-write-unlink` are denied on the workspace directory (rename/removal/replacement still denied); live test checks `touch`, `chmod` and `copytree` into the workspace. A flags deny was tried and removed because `copytree` sets flags on the destination. |
| V3 | minor | Clones keep BSD flags (`uchg`), leaving the evaluation copy behind and producing a misleading error. | Cloned files with flags have them cleared; live test sets `uchg` on a workload file. |
| V4 | minor | Runner `/proc/<pid>/stat` text parsing crashed on non-UTF-8 names; missing `/proc` crashed. | Binary parsing, `ValueError` handled, missing `/proc` fails closed with 125. Test with unusual names. |
| V5 | minor | `scandir` not closed on errors; vanished entries aborted the copy while unreadable files were skipped; streamed copies lost the mode. | Context-managed `scandir`; vanished entries and swapped links are skipped; other errors (for example an unreadable file) fail closed; streamed copies keep the permission bits. |
| V6 | minor | `-m`/`-c` warning only checked `argv[1]`. | Python options are parsed up to the script (`-u -m`, `-X dev -c`, `-mmodule`); other tools are not flagged. |
| Notes | — | `outputs_returned` semantics, later overwrite of returned workspace outputs, login-host-only Apptainer probe, zombie accumulation without an init. | Documented in `docs/execution-options.md`. |
