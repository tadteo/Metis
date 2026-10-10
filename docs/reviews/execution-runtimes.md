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
