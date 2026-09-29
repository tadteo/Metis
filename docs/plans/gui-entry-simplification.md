# GUI entry simplification

Base: `f1b402e`. The user requested removal of the workspace header and Commands
section, a brief writing animation for “Metis welcomes you.” on page entry, and a
classic moon/sun theme icon at the top right within the main workspace.

Scope: browser Home and shared workspace chrome only. Keep the existing question
handoff, sidebar navigation, research controls, persisted appearance, and scientific
behavior. Preserve the uncommitted Home question wording found on the integration
checkout by carrying it into this branch without changing that checkout.

Acceptance: no workspace bar or command palette appears or responds to its former
shortcut; the welcome writes once on initial entry, fades away after a few seconds,
and is immediately static/brief with reduced motion; the icon remains visible and
keyboard reachable on Home and Research at desktop and narrow widths; its accessible
name describes the next theme and switching persists through the appearance API.

Validation: inspect desktop and narrow browser renderings in both themes, exercise
keyboard access and the Home question handoff, run browser logic tests and relevant
repository checks. Obtain an independent review before commit and merge.

Implementation evidence on the original base: rendered Home in charcoal and cream at
desktop and 390px, and Research at 390px and 900px with a synthetic demo in a temporary
private Store. At 900px the icon was above the run title; the welcome was visibly
writing on reload and computed hidden after the delay. Keyboard Enter changed the
theme through the appearance API. A synthetic question carried into setup without
creating a run. Reduced-motion behavior was checked in the CSS and independent
review; no browser emulation of that preference was captured.

Validation on the original base: browser logic 49 passed; Python 878 passed and 3
skipped when socket and process permissions were enabled; Ruff lint and format,
public-file scan, and `git diff --check` passed. The first sandboxed Python attempt
had 809 passes, 12 failures, and 57 errors because it denied loopback sockets and
`ps`; it was not used as a product-failure signal. The initial Ruff run could not
write its worktree cache, so it was rerun with a temporary cache and passed.

Independent review found and resolved two medium-priority CSS issues: main padding
at 801–1100px and reduced-motion exit timing. The reviewer rechecked the revisions
and found no remaining actionable issue. See `docs/reviews/gui-entry-simplification.md`.

Integration note: `main` advanced to `df05400` during implementation. Its newer GUI,
connection, and accessible Home question changes must be preserved when this branch
is integrated. Recheck affected behavior after resolving any overlap.
