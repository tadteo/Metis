# Managed SSH from the web console

Implement connection profiles, explicit remote installation, SSH sign-in (including
MFA and host-key prompts), tunnel controls and a link to the remote research console.
Hosts may come from the local SSH configuration or be entered manually. Credentials
and keys remain under the local SSH client's control; prompt answers are transient.

The web layer owns only HTTP and browser presentation. `RemoteManager` owns profiles,
SSH subprocesses and tunnels; `remote_runtime` owns the remote controller lifecycle.
No scientific workflow changes or live SSH connections are part of this task.

Managed controllers require a supplied bearer token even for bootstrap, accept only
loopback forwarding authorities and exact matching browser origins, and disable
nested remote management. Local bootstrap behavior stays compatible. Browser tokens
arrive through a URL fragment, are removed from history immediately, and are retained
only in same-origin session storage for reload. SSH prompt answers are never stored.

Acceptance checks cover authenticated profile/actions, SSH prompt lifecycle, explicit
installation, manager cleanup, concurrent HTTP responsiveness, wrong/missing tokens,
duplicate headers, cross-site requests, forwarded ports, hostile display strings and
fragment handling. Run focused Python HTTP tests, browser logic tests, Ruff and mypy.
Parent integration obtains independent review before merging the focused commit.

## Validation and review

Completed: connection profiles and manual targets, in-app SSH prompts with transient
responses, explicit installation, persistent readiness diagnostics and tunnel links.
Managed bootstrap, health checks, forwarding authorities and nested-management denial
are covered by real local HTTP requests. No live SSH host or credentials were used.

- `tests/test_web.py`: 56 passed, using the transport worktree's actual `RemoteProfile`
  for validation and a controlled manager for subprocess-free HTTP routing.
- `node --test tests/test_web_ui.mjs`: 22 passed, including hostile display strings,
  fragment cleanup, reload tokens, MFA clearing/cancellation and persistent diagnostics.
- Ruff format/check, mypy for `web.py` against the transport worktree's interfaces,
  and `git diff --check`: passed.
- Coordinator independently reviewed the change and approved after the persistent
  diagnostic, dashboard-link polling and overlapping prompt-submit fixes. Integrated
  lifecycle tests and full-suite validation remain the coordinator's merge gate.

The isolated Python checks temporarily added the transport worktree to the package
search path; no transport source was copied or included in this web change.

## Independent transport review follow-up

The coordinator requested independent regressions while the transport owner repaired
review findings. `tests/test_remote_review.py` now exercises shutdown admission,
delayed terminal echo, failure/expiry cleanup, descendant processes, explicit host-key
approval, idempotent cleanup and visible termination errors. All eight passed against
the transport owner's final implementation, with watcher-thread warnings promoted to
errors; the focused Enter-response HTTP regression also passed (nine tests together).

The web follow-up accepts explicitly submitted empty SSH responses for prompts asking
the user to press Enter, and retains Python version/candidate diagnostics in readiness
reports. It does not change transport implementation. No live SSH was used for these
tests. The coordinator handles integrated browser visual inspection and deployment.
