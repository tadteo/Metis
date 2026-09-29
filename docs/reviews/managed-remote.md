# Managed SSH implementation review

Base: `0425e2a`; integration also retains guided setup from `3502385`.

Independent ownership/review: the terminal owner reviewed the controller and Store
changes (see [remote-runtime.md](remote-runtime.md)); the coordinating agent reviewed
the terminal and web implementations; the web owner independently reviewed SSH
authentication and process lifecycle. Review covered the user's requirements for
arbitrary new hosts, OpenSSH configuration discovery, in-interface MFA, separate
client/controller lifetimes and reconnection, plus existing research invariants.

Findings resolved during implementation:

- Separate database storage could pair one journal with another project's artifact
  root. The database now records and verifies the canonical artifact root.
- CLI authentication was closed before an ensuing operation could use it. Check,
  install and connect authenticate within the same manager lifetime; the standalone
  login command explicitly tests sign-in rather than promising persistent login.
- An MFA response submitted during terminal polling could be cleared unsent. Busy
  input is retained; accepted responses are cleared immediately.
- Status polling could remove a working access link. A same-profile connected status
  preserves it, and a profile change or disconnect invalidates it.
- Readiness errors needed persistent, actionable Python/filesystem diagnostics.
- Install/start ownership is coordinated through launch and controller lifetime locks;
  an active or uncertain controller cannot be silently overwritten by an update.
- Long client temporary paths can exceed OpenSSH's Unix socket limit. Managed sockets
  use a short private directory.
- Shutdown admission raced with child registration. The same lock now governs process
  creation and the closing transition, with a deterministic regression.
- Authentication cleanup must scrub responses and close PTYs even when termination
  fails. Tests cover real PTY host-key/password/MFA exchanges, delayed echoed material,
  cancellation, timeouts and process descendants.
- Empty replies are legitimate for SSH prompts asking the user to press Enter. Both
  interfaces allow explicitly submitted empty replies, without sending one automatically.
- Editable-package provisioning could include adjacent private files. Installation
  uses package/Git manifests and credential exclusions rather than copying the checkout.

The integration preserves all guided-setup handlers and saved configuration defaults.
Scientific execution, acceptance rules, budgets and immutable research artifacts remain
behind the existing engine. Disconnect is not pause or cancellation.

Validation and live deployment evidence are recorded in the task plan after the fully
integrated checks. These checks establish engineering behavior, not scientific parity
or publication quality. Site-approved persistent database storage and provider/runtime
configuration remain deployment prerequisites.
