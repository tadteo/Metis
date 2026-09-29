# Metis aesthetic guidance — independent review

Base reviewed: `ed4b656c4ff3d4a2f2a29b26aa6f011b672c2d2a`.
Scope: uncommitted documentation changes in `VIBE.md`, `AGENTS.md`, `README.md`,
`CONTRIBUTING.md`, `docs/development.md`, `docs/interface-voice.md` and the task plan.

## Result

Approved. No actionable findings within this documentation-only scope.

## Checks

- Compared the guidance against the user’s accepted identity, exact shared palette,
  restrained terracotta, browser-like TUI hierarchy and question-led setup needs.
- Read the writing-for-agents skill. The AGENTS pointer explicitly triggers before
  interface design or editing; contributor and development entry points reach the
  same authority. The former voice guide remains a compatibility pointer instead
  of maintaining a competing set of voice rules.
- Checked the implementation map against the actual source files and entry points.
  Theme tokens remain authoritative in interface.json, with appearance persistence
  separated from research configuration. Presentation and shared setup ownership
  match the existing modules.
- Checked acceptance guidance for observable outcomes: both themes, terminal sizes,
  narrow browser layout, keyboard focus, complete evidence access, retained edits,
  missing setup, failure states and no implicit execution during navigation.
- Confirmed scientific instructions, complete negative evidence, measured-evidence
  claims, public synthetic artifacts and the established delivery workflow retain
  precedence. No runtime, prompt or scientific behavior files were changed.
- All 55 local Markdown links in the six design/entry-point documents resolve.
  `git diff --check` passed. Runtime tests were not run because this change contains
  only documentation; no runtime validation claim is made.
