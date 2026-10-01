# Coding worker architecture explanation

Base: `66aab17`. Explain the existing agentic coding architecture and propose how
parallel coding and experiment execution would fit. This is a documentation-only
answer to the user's design question; no runtime refactor is authorized by this task.

Trace the coding specialist, tool loop, experiment engine, executor and persistence.
Verify Claude Code source availability against official sources. Save a cited design,
separating existing behavior from proposals. Reuse the free managed execution-options
worktree on an isolated branch. Check references, whitespace and public artifacts,
obtain independent review, commit and merge. Runtime tests are unnecessary for prose.

Completed: saved `docs/coding-worker-design.md`; independent review approved without
findings (see `docs/reviews/coding-worker-design.md`). Local links, whitespace and
public-file scan pass. Documentation only; runtime implementation remains proposed.
