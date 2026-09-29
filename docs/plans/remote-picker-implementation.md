# Compact SSH workspace picker

Source requirement: the user approved prototype A on `codex/remote-quick-connect` at `fe2690a`: the bottom-left “Connected to localhost” status becomes the button for a compact picker near the top of the browser console. The picker should make local versus SSH workspace clear and let a saved host connect with one primary action. The existing detailed connection settings remain reachable for first-time setup and diagnostics.

Integration base: `f1b402e` on `main` when the implementation branch was checked and reviewed. Implementation branch: `codex/remote-picker-implementation` in a separate managed worktree. The main checkout has unrelated concurrent UI changes; preserve them during integration. This change owns browser HTML, CSS, browser interactions/tests, user guidance and interface review evidence. It does not change scientific execution or SSH transport contracts.

User journey and acceptance:

1. In the local browser console, the status at bottom left opens a compact, keyboard-accessible top dialog. It shows the current local workspace, saved SSH profiles and discovered aliases. Search filters by visible name/host. Host text is inert and focus returns to the status control on close.
2. Choosing a saved profile offers one Connect action. Existing SSH authentication is reused; password, host-key and MFA prompts remain transient in the existing secure prompt dialog. Successful connection shows an explicit private dashboard link. Failure shows a specific next step and keeps the full connection settings reachable. Installation remains explicit.
3. Choosing an unsaved alias or entering a new target leads into the existing profile form with the target filled. Existing draft edits are not erased merely by opening the picker. Local and remote status labels are clear. A managed remote dashboard does not expose nested SSH management.
4. The compact dialog fits desktop and narrow viewports in light and dark themes. Keyboard navigation, focus, missing setup, busy, disconnected and failed states are inspected in a browser. Synthetic screenshots and interaction notes go in this plan/review.

Validation: focused browser logic tests, web HTTP tests, relevant lint/type checks, visual inspection, independent review, commits, then merge only after the unrelated main checkout is ready for integration. Offline tests and synthetic UI evidence do not validate live SSH/MFA or research quality.

Visual inspection on the local scratch console (synthetic `fixture-example` profile, no SSH connection): [light theme](../evidence/remote-picker-light.png), [dark theme](../evidence/remote-picker-dark.png), and [390 px viewport](../evidence/remote-picker-narrow.png). The status button opened the top dialog, the form handoff filled a new host, and Escape returned focus to the status. A long local SSH alias list stayed inside a scrolling options area. The approved prototype remains on `codex/remote-quick-connect` at `fe2690a`.
