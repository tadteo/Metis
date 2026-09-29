# Metis interface independent review

Reviewed uncommitted interface changes against integration base `36fecfe` in the
separate `metis-interface-review` checkout. Review covered the accepted charcoal/cream
Greek aesthetic and usability plan, GUI/TUI/CLI behavior, private preference persistence,
settings preservation, keyboard navigation and managed SSH integration. The reviewer did
not author or modify implementation. No model requests or real SSH connections ran.

## Findings

1. **P1 — focused TUI navigation returns to the outgoing page.**
   `src/autoresearch/tui.py:756` switches TabbedContent without transferring focus out
   of the old pane; `select_run` at line 1172 bypasses the navigation helper as well.
   With one synthetic saved run, call `action_runs()`, wait for UI events, then
   `action_welcome()`: the view briefly becomes Home and is restored to Runs when
   Textual focuses the old pane's New research button. Pressing Enter on the Runs
   table likewise fails to remain on Overview. This obstructs normal saved-run
   inspection. Move focus safely during every route change and test the final view
   after queued focus/activation events settle, using actual keyboard row selection.
   Status: resolved and independently verified. `_navigate` now transfers focus to the
   persistent view selector, and `select_run` uses it. The original 80×24 pilot
   reproduction now remains on Home and Enter from Runs opens Overview.

2. **P2 — invisible execution shortcuts remain active in setup.**
   `src/autoresearch/tui.py:295` retains global Ctrl+S/Ctrl+R while `_sync_navigation`
   hides the selected-run summary and execution controls on Settings/Home/New.
   A synthetic-run test with a spy in place of `controller.start` confirmed that
   Settings → Ctrl+S submits one research step despite all execution controls being
   invisible. Save muscle memory can therefore start a selected live run without
   visible run context. Make execution bindings contextual to research views; keep
   pause available globally. Treat SSH connections as a non-research page too.
   Status: resolved and independently verified. `_start` rejects execution while
   contextual controls are hidden, including the SSH connections view. The original
   spy reproduction now records zero starts; the new regression test also confirms
   stepping still works from Overview.

3. **Documentation follow-up.** `docs/usage.md:61` still describes the removed
   sidebar/tab navigation, and the managed SSH guide still refers to a Remote tab.
   Update navigation, keyboard help, appearance persistence and terminal status/JSON
   behavior along with the already-planned fidelity evidence update.
   Status: resolved. Reviewed updated usage and managed SSH instructions, including
   command search, section navigation, theme persistence and explicit JSON output.

## Evidence

- `node --test tests/test_web_ui.mjs`: **30 passed**.
- Initial focused Python run of appearance/TUI/settings/web: **33 passed, 4 failed,
  54 errors**. All failures/errors were localhost socket creation denied by the
  filesystem/network sandbox (`PermissionError`), not behavioral assertions.
- Re-ran `tests/test_web.py` with loopback test permission: **60 passed**.
- Independent Textual 80×24 pilot probes confirmed Settings command-palette search
  and selection, persistent section edits, and the two navigation/shortcut findings.
  Execution was replaced with a spy; no research was started by the review.
- Appearance endpoint stays behind existing request authentication and origin checks;
  persistence is separate from ResearchConfig, and invalid theme values are rejected.
- Existing SSH authentication, token bootstrap, inert rendering, installation and
  tunnel actions remain represented by the passing Python/Node regression checks.
- The CLI retains all existing subcommands and explicit `status --json`; pipe output
  remains JSON. No scientific execution or evidence-gate implementation changed.

Visual acceptance and full release validation are the implementer's separate evidence.
Deterministic tests do not establish live scientific quality or deployment readiness.

## Resolution check

Re-ran the original independent navigation and hidden-shortcut reproductions against
the corrected implementation: both fixed. `tests/test_appearance.py`: **4 passed**
(the only warning was inability to write pytest cache inside the sandbox). No remaining
actionable review findings in this interface diff. Full release validation, fidelity
evidence and visual acceptance remain the integration owner's required merge gates.
