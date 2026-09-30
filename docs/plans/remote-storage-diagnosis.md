# Remote connection storage diagnosis

Source requirement: after the compact SSH picker merged, the user reported that a saved cluster connection failed with `Database directory uses nfs4`. The intended outcome is a usable login-host workflow without risking research history or weakening SQLite storage checks. The user wants to select research storage privately from connection settings because home storage is limited and project storage is separate.

Integration base: `59f0730` on `main`. The live console, SSH account, storage paths and screenshot are private; do not add them to Git.

## Reproduction and observations

- A temporary read-only probe of the local console's saved profile failed twice with `ready=False`, `database_filesystem=nfs4`, and the database-directory error. An initial unauthenticated HTTP probe returned 401; no remote diagnostic was inferred from that response.
- The saved profile had no explicit state or database directory. `remote_runtime._settings()` consequently placed SQLite under the default remote state directory on shared home storage. Repeating **Check remote** returned the same NFSv4 readiness problem. No install, controller start or research run was requested during diagnosis.
- Read-only SSH mount checks reported NFSv4 for home and project storage and XFS for temporary local directories. The SSH alias reached different login hosts across attempts. No user-writable durable host-local directory was evident. A noninteractive shell printed unrelated startup errors; the remote check itself completed.
- [SQLite WAL guidance](https://www.sqlite.org/wal.html) excludes network filesystems. The existing network-filesystem rejection protects durable research history; the picker rendering was not the failure.

## Hypotheses tested

1. **Confirmed:** the blank database directory resolves to NFSv4. The profile form and remote probe agree.
2. **Rejected:** an already configured host-local directory was misclassified. The field was blank and mount inspection confirmed the default path was NFSv4.
3. **Rejected:** the picker used a stale saved profile. A fresh authenticated probe and browser check returned the same result.
4. **Not established:** a site-approved, persistent user-writable host-local directory exists. Only temporary local paths were found; do not use them for durable history without explicit site support.

## Resolution boundary

The user prefers a login-host controller and wants to choose the actual project path privately in connection settings. The research-files setting is implemented and merged as `f354f24`; no real project path was supplied or committed. A durable connection remains unresolved because the observed home and project mounts are NFSv4 and no approved persistent host-local database path has been established. Keep the SQLite guard. If a suitable directory becomes available, verify ownership, write access, retention/backup policy and login-host pinning before configuring the profile; then rerun the probe and validate controller lifetime. Temporary local storage must not be presented as durable research support.

The existing Slurm backend assumes local `sbatch`, `squeue`, `sacct` and `scancel` on a cluster host. A controller on another machine would require explicit workspace transfer, scheduler receipt and resumption contracts.

## User correction: choose research storage

`RemoteProfile.state_dir` selects research files and experiment workspaces, but the GUI had hidden it under advanced settings and called it a state directory. `RemoteProfile.directory` selects the installed Python environment and controller log. The settings now show research files directly, with a generic placeholder, and keep the separate database directory under advanced settings with the network-filesystem warning. Profile choices remain in local private configuration. The probe shows the resolved paths. The connection still needs suitable durable database storage before it can be considered ready.
