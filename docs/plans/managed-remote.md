# Managed SSH connections

Source requirement: users can connect AutoResearch to any SSH host, discover existing
OpenSSH aliases, and authenticate (including MFA and first-use host verification) from
the CLI, Textual console, and web console. Berzelius is a private live target, never a
hardcoded default or public fixture. The remote controller survives client disconnects.

Integration base: `0425e2a`. Independent task branches own transport/authentication,
web, and terminal/CLI interfaces. This branch owns the remote controller lifecycle,
optional separate database directory, integration, documentation and review records.

The transport delegates SSH policy and authentication to OpenSSH, retaining private
keys locally. Explicit provisioning transfers only the installed application package
and installs pinned dependencies in a remote user virtual environment. No research
files, provider keys, or local environment variables are copied automatically.
Remote run creation still uses the existing validated research interfaces.

The remote controller listens on loopback and requires a capability for bootstrap;
an SSH tunnel exposes it to the initiating client. Durable controller descriptors and
logs are private. Reconnecting discovers and checks the existing controller instead
of duplicating it. Disconnecting closes local SSH children, not remote research.

Acceptance checks:

- SSH config discovery, arbitrary new hosts, safe argument/path handling, authentication
  prompts, cancellation, reconnect and tunnel cleanup through the public manager.
- Authenticated web routes and origin/host checks, secret-free profiles and transient
  authentication replies; terminal interactions remain responsive.
- Real local controller startup, readiness, duplicate-start prevention and reconnect;
  detached lifecycle independent of the spawning process; stale descriptors handled.
- Database directory can be separate from shared experiment files. Network filesystem
  limitations are surfaced before a managed controller begins writing SQLite WAL.
- Focused regressions followed by CI-equivalent offline checks and independent review.
- Live SSH checks/provisioning only on the user-authorized target; report MFA or cluster
  policy/runtime limitations precisely, without treating offline tests as live proof.

Remote controller deployment must follow the host's process policy. It is detached and
resumable, not a system-level restart guarantee after host reboot or allocation expiry.

## Integration with guided setup

Main advanced to `3502385` during implementation. The terminal owner first reconciled
its controls with that exact guided-setup change. The integration branch then retained
both sets of web handlers/dialogs/tests and the optional `--db-dir` argument; the
settings CLI uses the same database selection. The remote controller leaves launch
configuration unset when no file is selected, so saved remote defaults remain effective.

After conflict resolution, 113 combined interface/settings/runtime tests passed and
the remaining profile-validation test passed with the transport branch supplied on
the package search path. All 26 merged browser tests and the five-module type check
passed. Final validation will rerun these against the fully integrated source tree.
