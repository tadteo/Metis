# Independent managed remote runtime review

Reviewer: terminal-integration agent, independent of the runtime/Store implementation.
Reviewed against `0425e2a`: `src/autoresearch/remote_runtime.py`, the database-directory changes to `src/autoresearch/store.py`, and `tests/test_remote_runtime.py` in the managed-remote integration worktree.

## Finding and resolution

**P2 — Bind split database storage to its artifact root.** The first Store change allowed two different state directories to share the same explicit database directory. Both could list the same run metadata while resolving source/artifact paths against different roots. The coordinator added a singleton storage-identity table recording the canonical artifact root, rejected a conflicting root, and added `test_database_cannot_silently_pair_with_a_different_artifact_root`. Reinspection confirms first registration is serialized by SQLite, existing identity is checked, and the registration transaction commits before the accounting migration starts its own transaction. Finding resolved.

## Remaining review result

No further actionable runtime or storage findings were identified in the reviewed scope. Startup serializes launcher/controller ownership, reconnects only to a matching authenticated controller, refuses foreign-host descriptors and unresponsive live processes, and does not kill an unrelated process based on a stale PID. Descriptor/log permissions and regular-file checks protect the private controller capability; startup rejects known network filesystems for the SQLite database while allowing separate shared experiment storage. Remote controller shutdown preserves the web server's existing checkpoint-worker handling.

Independent focused verification: eight runtime/storage tests passed with the live controller-startup test deselected because that path awaits the separately owned web constructor integration. The initial sandboxed attempt could not bind a test loopback socket; the authorized rerun succeeded. Full controller startup/reconnect and web bootstrap protection remain integration checks for the coordinator, and institutional SSH/MFA and host storage policies remain deployment-specific validation.
