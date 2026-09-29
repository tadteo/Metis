# Managed remote terminal integration

Base: `0425e2a`. Branch: `codex/remote-terminal` in its isolated worktree.

## Requirement and boundary

Expose the shared managed SSH transport through the public CLI and a Remote tab in the Textual console. Users can choose SSH configuration entries or enter a new host/user/port, save named profiles, sign in interactively including MFA, check readiness, explicitly install, connect, inspect status, open a private tunneled dashboard and disconnect. Remote research and its controller survive a local tunnel disconnect. Installation stays an explicit action; no arbitrary shell facility or credential persistence is introduced.

Owned implementation: `cli.py`, `tui.py`, their tests, and this plan. The transport manager and remote runtime belong to sibling branches. Both interfaces use `RemoteManager(root=store.root)` and validated `RemoteProfile` records, so profile persistence is shared.

## Acceptance criteria

- CLI commands discover/list/add/check/install/login/connect/status/disconnect; connect owns its tunnel until interruption and optionally opens the browser.
- The Remote tab offers editable host and paths, saved profiles, discovered host choices, sign-in prompts with masked input and Send/Cancel, and explicit install/connect/disconnect/open controls.
- SSH, bootstrap and authentication polling run off the Textual event thread. Secrets are cleared immediately and never written to Store events or profile files. Authenticated URLs appear only in their intentionally private access field or explicit CLI connect output.
- Closing the UI closes local tunnels/authentication sessions without stopping remote research. Local research retains existing checkpoint shutdown behavior.
- Offline tests use a fake manager and assert command dispatch, secret handling, tunnel lifecycle, MFA submission/cancel, remote errors and responsive navigation. Existing CLI/TUI tests remain green.

## Validation and integration

Run focused CLI/TUI pytest, Ruff and mypy with this worktree's `PYTHONPATH=src`. The coordinator obtains independent review before integration. A real remote deployment and institution-specific authentication policy remain explicit target-host checks, separate from mocked transport tests.

## Implemented behavior and verification

The CLI includes `remote hosts`, `list`, `add`, `login`, `check`, `install`, `connect`, `status`, and `disconnect`. `check`, `install` and `connect` authenticate interactively within the same manager lifetime, so MFA authorizes the requested operation. `login` explicitly verifies sign-in and closes its owned session when the command exits. Authentication diagnostics use stderr; operation results use JSON stdout. `connect --open` opens the private access link and owns the tunnel until interruption.

The Remote tab keeps sign-in and operation calls on background workers, polls authentication at a bounded interval, masks submitted answers, clears accepted responses immediately, and preserves unsent input if a poll is busy. It keeps the authenticated URL in a dedicated private field, opens it only by explicit action, and associates retained links with the exact profile. Closing the application waits for active work and releases managed connections.

Coordinator independent review identified and resolved three issues: successful CLI authentication was initially torn down before an operation; Enter during an authentication poll could discard an unsent response; and a token-redacted status response could erase the existing dashboard URL. Regression tests now cover all three, including cross-profile URL isolation.

Validation: 39 focused CLI/TUI tests passed; Ruff passed; mypy passed for both modules against temporary copies of the sibling transport/authentication modules. Those copies were removed before commit. Tests use public synthetic hosts and fake managers, so they do not claim a successful live institutional SSH/MFA deployment. The coordinator approved the terminal review after these corrections.

## Guided setup integration

Merged main revision `3502385` into the remote-terminal branch after its independent guided-setup review. The only textual conflict was `ResearchApp.pressed`: both branches added an initial button-dispatch branch. Resolution keeps remote commands first and the welcome/settings/import/check/save branches immediately afterward, preserving each action's existing behavior. CLI registration, saved configuration defaults, first-launch welcome selection and settings tests merged automatically. Main's other additions were carried unchanged. No global database-directory CLI option was added here; that remains the coordinator's integration change.

Validation after resolution: 58 tests passed across `test_cli.py`, `test_tui.py`, `test_settings.py`, and `test_setup.py`; Ruff passed for the affected interface/settings files and tests; mypy passed for CLI, TUI, settings and setup CLI against temporary sibling transport modules. Temporary modules were removed before the merge commit. Main itself was not modified by this integration.
