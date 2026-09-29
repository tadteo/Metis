# Compact SSH workspace picker review

Independent review of the browser implementation diff by a separate agent against implementation base `f1b402e`, following `docs/development.md` and the accepted option A prototype (`fe2690a`). The reviewer inspected correctness, SSH/auth boundaries, accessibility, regressions and the light/dark screenshots. No live SSH or MFA session was attempted.

## Findings and resolution

1. **P2, resolved:** The first picker version remembered a connected tunnel only in browser memory. After a page reload it offered Connect instead of the open-dashboard and disconnect actions. Opening the picker now queries the server status for each saved profile, keeps only validated loopback dashboard links, and selects a connected profile by default. A reload regression test covers the response and actions.
2. **P2, resolved:** A generated name for a new host could collide with a saved profile, causing a save to replace that profile and close its tunnel. Generated names now use a unique numeric suffix, while preserving the profile-name length limit. A regression test covers successive collisions.
3. **P3, resolved:** The selected workspace was marked visually without an accessible selected state. Workspace buttons now set `aria-pressed` on every render; the browser logic test checks its value.

The reviewer rechecked all three fixes and reported no remaining blocking findings. Host text renders inertly, existing SSH prompts remain explicit, and dashboard navigation uses the existing loopback URL validation. This software review does not establish live cluster compatibility or scientific capability.

## Validation and visual evidence

- `PYTHONPATH=src …/pytest -q tests/test_web.py`: 63 passed.
- `node --test tests/test_web_ui.mjs`: 55 passed after the fixes; reviewer independently ran the same suite.
- `PYTHONPATH=src …/pytest -q`: 878 passed, 3 skipped.
- `ruff check .`, `ruff format --check .`, `mypy src`, `metis validate-specs`, `scripts/scan_secrets.py`, `node --check src/autoresearch/static/app.js`, and `git diff --check`: passed.
- Browser scratch console: bottom-left status opened the compact top picker; a synthetic host filled the detailed setup form; Escape closed the picker and restored focus. The saved-host list scrolls. [Light](../evidence/remote-picker-light.png), [dark](../evidence/remote-picker-dark.png), and [narrow](../evidence/remote-picker-narrow.png) screenshots contain a synthetic fixture host and no live SSH connection.

Remaining external evaluation: a real target host, its authentication policy and its runtime installation have not been tested. The existing server-side SSH and installation behavior is unchanged by this browser task.
