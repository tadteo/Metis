# GitHub documentation readiness review

Base: `ca281094a5f3c5151517f9a401fae167c13c4271`. Scope: the
`codex/github-documentation` task and its [plan](../plans/github-documentation.md).
The `documentation_review` agent inspected an exact candidate snapshot in a separate
checkout, read the project standards and compared instructions with implementation.
The reviewer made no edits. This records independent findings, not an author-only
certification.

## Findings and resolution

1. **P2: obsolete web settings paths.** The proposed first-run instructions used
   Workspace settings → Model access and browser Settings → Execution. The actual
   Settings entry opens Available to Metis; experiment compute belongs to New
   research → Project → Execution → Review. Corrected the README, first-run guide,
   usage, troubleshooting and affected reproducibility/Laya guidance. The author
   additionally confirmed the live console's Add provider → Add to Metis and
   Configure → Save model forms without changing credentials or starting research.
2. **P2: writer provisioning used system Python.** The linked writer guide's bare
   `python -m` did not use the uv-installed package. Changed it to `uv run --no-sync
   python -m autoresearch.paper_orchestra_setup` and documented concrete private
   settings / Advanced JSON / configured CLI application.
3. **P2: native writer credential source.** Compatible text models can resolve
   vault/session keys, but native Google grounded search/image and default native
   Semantic Scholar access read environment variables. The reviewer reproduced
   this distinction offline. The writer guide now names controller-launching
   `GEMINI_API_KEY` and optional `SEMANTIC_SCHOLAR_API_KEY`; Getting started calls
   out the Google requirement too.

The reviewer rechecked all corrections and returned **Approved**, with no remaining
actionable findings. Scientific limitations, synthetic labels, private-state and
budget distinctions remain explicit; removed README details stay reachable through
specialist guides.

## Independent validation

- Documentation link/image/anchor and generated CLI check passed.
- Four documentation tests passed, including broken destinations, missing anchors,
  unindexed targets and CLI drift / terminal-width stability.
- Focused Ruff lint/format checks, CLI help and `git diff --check` passed.
- Generated help includes nested SSH commands and their options.

Paid providers, runtime provisioning, live compute and rendered GitHub pages were
not independently exercised. Coordinator checks and published CI are recorded in
the task plan. Software validation does not certify scientific performance.
