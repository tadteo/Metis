# Berzelius connection failure

Source requirement: after the compact SSH picker merged, the user reported “it is not working” and supplied a screenshot of the saved Berzelius connection failing with `Database directory uses nfs4`. The intended outcome is a usable Berzelius workflow without risking research history or weakening SQLite storage checks.

Integration base: `59f0730` on `main`. Work on `codex/berzelius-connection` in an isolated worktree. The user’s live console and remote account are private; do not add its run data, credentials, paths or screenshot to Git.

## Reproduction and observations

- A temporary read-only probe at `/private/tmp/metis-berzelius-probe.py` obtains the local console capability in memory, calls the saved profile’s `/probe`, and asserts readiness. It failed twice in about 1.5 seconds with `ready=False`, `database_filesystem=nfs4`, and the exact database-directory error. An initial unauthenticated HTTP probe returned 401; no remote diagnostic was inferred from that response.
- In the live connection form, the saved profile has no explicit state or database directory. `remote_runtime._settings()` consequently places SQLite under the remote state directory, which is below the NFS home mount. Repeating **Check remote** in the browser returned the same NFSv4 readiness problem. No install, controller start or research run was requested during this diagnosis.
- Read-only SSH mount checks reported NFSv4 for home and project storage and XFS for `/tmp` and `/var/tmp`. The login alias reached a named Berzelius login node in two attempts. There was no user-writable durable host-local directory evident. The noninteractive login printed unrelated `module: command not found` lines from `.bashrc`; the remote check itself completed.
- [The current Berzelius storage guide](https://hpc.pages.naiss.se/user-documentation/berzelius-docs/storage/) identifies home/project as shared storage and compute-node `/scratch/local` as temporary, erased between jobs. [SQLite WAL guidance](https://www.sqlite.org/wal.html) excludes network filesystems. The existing network-filesystem rejection is therefore a research-integrity boundary, not a picker rendering failure.

## Hypotheses tested

1. **Confirmed:** the blank database directory resolves to NFSv4. The live profile form and remote probe agree.
2. **Rejected:** an already configured host-local directory was misclassified. The field is blank and mount inspection confirms the default home path is NFSv4.
3. **Rejected:** the picker used a stale saved profile. A fresh authenticated probe and browser check returned the same result.
4. **Not established:** a site-approved, persistent user-writable host-local directory exists. Only temporary local paths were found; do not use them for durable history without explicit site support.

## Resolution boundary

The user has been asked whether they have an approved persistent host-local database/controller directory, or want a laptop-owned controller with SSH/Slurm remote execution. Keep the existing SQLite guard. If a suitable directory is supplied, verify its owner, write access, retention/backup policy, and login-host pinning before configuring the profile; then rerun the probe and connection feedback loop and validate controller lifetime. Otherwise, design the local-controller route with explicit workspace transfer, scheduler receipt and resumption contracts before implementation. The existing Slurm backend assumes local `sbatch`, `squeue`, `sacct`, and `scancel` on a cluster host, so this is new integration work. Do not present a temporary `/tmp` smoke connection as durable research support.

## User correction: choose research storage

The user wants Metis to remain on a Berzelius login node and to place research files in their separately mounted project storage, because home has limited space. `RemoteProfile.state_dir` already selects the research-file and experiment-workspace root, but the GUI hides it under advanced settings and calls it a "state directory." This is a usability defect distinct from the database prerequisite. `RemoteProfile.directory` selects the installed Python environment and controller log; users with a small home quota may also place that dedicated directory on project storage. Both paths should be explained without implying project storage is safe for the SQLite database.

The user prefers to choose the exact project directory in the interface because the repository is public. Do not add their real path to code, tests, documentation or Git history. Save the selection in the local private remote profile and show a generic placeholder only.

Implementation boundary: promote the research storage path to the primary saved-connection form, label it plainly, describe the project-storage use case and default, and keep the separate database path in advanced settings with an explicit network-filesystem warning. Name the picker entry **Connection settings** so the user can find the saved-profile form. Align the TUI and user guide terminology. Preserve saved profile values and the compact picker. Do not change the network-filesystem guard or select temporary scratch automatically.

Acceptance: the GUI and TUI make the research-files/project path discoverable, saving and reopening a profile preserves it, a probe shows the actual resolved research and database locations, keyboard and light/dark views remain usable, and focused remote/UI tests pass. The live Berzelius connection remains blocked until a safe database location or a separately approved architecture is established; do not report the storage control as a connection fix.
