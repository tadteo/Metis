# Managed SSH connections

Source requirement: users can connect AutoResearch to any SSH host, discover existing
OpenSSH aliases, and authenticate (including MFA and first-use host verification) from
the CLI, Textual console, and web console. Live SSH targets remain private and are
never hardcoded defaults or public fixtures. The remote controller survives client disconnects.

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


## Final implementation and validation

The independent Metis identity change from `5f0cdd3` was merged before final checks.
The remote installer now builds `metis-research` with both `metis` and the compatible
`autoresearch` entry point. The only identity merge conflict retained the Metis brand
and the remote location indicator. Public runtime paths and environment variables
remain compatible with existing state.

Final implementation: `1a3f3b4` (including transport `9176f40`, terminal `f999544`,
web `9e58828`, lifecycle regressions `fa8f14c`, runtime/storage `cc28bc3`, identity
integration `0e794bb`, and browser/profile edge fixes `c78cfab` and `5cbcc04`).

Validation on 2026-09-29:

- Full offline suite: 836 passed, 3 skipped. The optional wheel check and two
  opt-in pinned-upstream environment checks were skipped in that ordinary run.
- After the final browser-hostname/profile-routing fixes, all 63 affected web and
  bootstrap tests and all 28 Node browser tests passed.
- Ruff format and lint passed; mypy passed for all 65 source files. AI specification
  validation, public-file scanner and scanner self-test passed.
- The built wheel was loaded outside the checkout, its entry points and packaged
  definitions were checked, and an installed synthetic workflow completed.
- The isolated CLI synthetic demonstration completed. This is control-flow evidence,
  not a live model or publication-quality evaluation.
- A real browser accepted and saved a new manually entered SSH target, displayed
  optional port/key/runtime settings and enabled the sign-in controls. No connection
  to the synthetic example host was attempted.

A user-authorized cluster smoke test installed the actual package using Python 3.11,
opened an authenticated dashboard through OpenSSH forwarding, rejected unauthenticated
bootstrap requests, and verified zero research runs. The controller survived tunnel
disconnect and a fresh client reconnected to the same process. The empty test controller
was then stopped gracefully; the application installation remains available. The SSH
session used the user's existing authenticated connection. Fresh password/MFA exchanges
were exercised with real PTYs and interface regressions, not with a live cluster MFA
challenge. No provider credentials, paid calls or scheduler jobs were used.

The host's shared home/project filesystem uses NFS, so this smoke deliberately used
an isolated temporary XFS database. That is disposable test storage, not a production
configuration. Durable deployment still requires a site-approved persistent,
SQLite-compatible database path, suitable controller-host policy, and remote provider
configuration. Default shared-storage readiness reports this prerequisite.

The first two live smoke harness attempts stopped their own empty controllers after
incorrect harness assumptions (expecting HTTP403 instead of401, and expecting private
controller identity in a deliberately redacted public probe). The final harness used
the correct status contract and passed; no application workaround was introduced.
