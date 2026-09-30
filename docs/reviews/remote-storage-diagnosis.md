# Remote connection diagnosis review

Base: `59f0730` on `main`. Scope: the diagnosis and resolution boundary in `docs/plans/remote-storage-diagnosis.md`; no runtime behavior was changed.

An independent agent reviewed the stored profile fallback, remote probe and startup checks, cluster storage guidance, SQLite WAL requirements and the Slurm backend contract. It confirmed that the blank database setting reaches NFSv4 and that the startup guard is appropriate. It found no established durable, user-writable host-local database path on the tested login hosts. It also confirmed that a controller on another machine requires new remote scheduler and workspace-transfer integration, not a profile-only change.

Actionable finding: state the exact-host, write-access and retention checks needed for any path supplied later. Resolved in the plan. A durable connection remains contingent on an approved storage path or another reviewed architecture. No temporary local directory was configured and no research run was started.
