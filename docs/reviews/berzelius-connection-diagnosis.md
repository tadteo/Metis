# Berzelius connection diagnosis review

Base: `59f0730` on `main`. Scope: the diagnosis and resolution boundary in `docs/plans/berzelius-connection.md`; no runtime behavior was changed.

An independent agent reviewed the stored profile fallback, remote probe and startup checks, the cluster storage documentation, SQLite WAL requirements, and the current Slurm backend contract. It confirmed that the blank database setting reaches NFSv4 and the startup guard is appropriate. It found no documented durable, user-writable host-local database path on Berzelius. It also confirmed that a laptop-owned controller requires new remote scheduler and workspace-transfer integration, not a profile-only change.

Actionable finding: cite the current NAISS Berzelius storage guide and state the exact-host, write-access, and retention checks needed for any path supplied later. Resolved in the plan. A durable connection remains contingent on the user's route choice or an approved storage path. No temporary local directory was configured and no research run was started.
