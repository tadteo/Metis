# README first impression

Base: `70a1840`. User request (2026-10-07): make the project understandable and
tryable within a minute, because the public repository has no outside users yet.

## Boundary

README structure and copy only, plus screenshots in `docs/images/`. No runtime,
scientific contract or interface change. Existing sections are kept; the long
disclaimer moves from the opening into "Status and scope" without weakening it.

## Acceptance

- Opening states what Metis does and its differentiator in two short paragraphs.
- A real screenshot of the console (light/dark via `<picture>`) and the TUI, both from
  the offline demo and labelled as scripted/synthetic.
- A copy-paste quick start that needs no account or spending.
- Every claim is traceable to existing docs: failure retention (paper-spec), protected
  evaluator (examples/README), claim integrity (claim-integrity.md), budget reservation
  (accounting.md), versioned specs (ai-system.md).
- Copy follows VIBE.md voice: literal actions, no omniscience or mysticism.
- `scan_secrets.py` and README-referencing tests pass; independent review recorded.

## Evidence

- Screenshots: `metis demo` in an isolated `AUTORESEARCH_HOME`, `metis serve --port 8777`,
  captured with headless Chrome at 1440×900 (charcoal and cream themes); TUI rendered
  with Textual `run_test(size=(150, 44))` and rasterized. No private state appears.
- `scan_secrets.py`: passed. `pytest tests/test_onboarding.py tests/test_setup.py
  tests/test_source_policy.py tests/test_web.py tests/test_fidelity_matrix.py
  tests/test_package.py`: 166 passed, 1 skipped.
- Quick start verified in this worktree: `uv sync --frozen --group dev` then
  `uv run metis demo` completed in 38 s; `metis tui` accepts no arguments.
