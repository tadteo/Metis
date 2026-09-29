# Managed SSH transport

Requirement: connect the local web/TUI to an independently running remote AutoResearch
controller through system OpenSSH, including interactive MFA, without exposing tokens
or retaining authentication answers. Base: `0425e2a`.

Owned boundary: `remote.py`, internal `ssh_auth.py`, and their focused tests. Remote
runtime, server authentication and UI integration are coordinated separately.

Implementation: private strict profiles; concrete SSH alias discovery with Include;
PTY authentication with managed ControlMaster sockets; explicit idempotent package-only
installation; JSON helper calls; ready-checked forwarding, bounded reconnect and cleanup.
Remote code comes only from the installed package and pinned direct dependencies.

Acceptance checks: quoted hostile arguments; Include recursion; profile/token privacy;
password/MFA/host-key interaction, echo suppression, timeout/cancellation; failed helper
and install handling; authenticated tunnel readiness and reconnection. Offline tests
must not contact a cluster. Actual remote access remains unverified until authorized
credentials and cluster policy permit an integration run.

Validation: 26 owned transport/authentication tests and 12 independently written
bootstrap/lifecycle tests passed together (38 total, 5.16 seconds), with background
thread exceptions treated as failures. Ruff format/check and strict mypy passed for
both modules. The independent tests are integrated by their owning branches.

Independent review: the web agent and coordinator checked host trust, package-only
installation, prompt privacy, shutdown races, process descendants, installer locks,
diagnostic usefulness and authentication lifetime. Their reproduced findings were
fixed and checked before coordinator approval. In particular: host-key approval is
explicit, shutdown and child admission are synchronized, late terminal echoes are
discarded, failed authentication clears answers, and cleanup failures remain visible.

The remote helper uses `directory/venv/bin/python -m autoresearch.remote_runtime`.
Interactive authentication owns a private short ControlMaster socket; existing
user-owned masters can be borrowed. Forwarding uses explicit `-O forward`/`cancel`
and authenticated HTTP readiness. Closing the local manager terminates its own SSH
carriers but never stops remote research or a borrowed user-owned SSH master.

The coordinator owns live provisioning and end-to-end UI validation after integration.
No cluster installation or live research run was performed by this branch.
