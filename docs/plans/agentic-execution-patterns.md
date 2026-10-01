# Related agentic execution patterns

Base: `804c33b`. User asks how similar scientific-agent papers and general coding
agent systems handle parallel experiments and isolated implementation work.
Documentation-only research: compare primary AI Scientist-v2/AIDE source, official
coding-agent worktree guidance and experiment scheduling documentation. Separate
observed implementation from proposed Metis design. Preserve unpublished upstream
limits; do not add a scheduler or change scientific behavior in this task.

Reuse the clean, free execution-options managed worktree on a new task branch.
Save a dated, cited report in docs, check local references and whitespace, obtain
independent source review, commit and merge. No runtime tests required for prose.

Completed report: `docs/agentic-execution-patterns.md`. Primary sources include
Sakana's parallel implementation and AIDE's sequential runner, deliberately
separating those projects from ScientistTwo and the commercial Weco service.
Independent reviewer `/root/execution_review` approved without findings; source
and review limitations are retained. Local links resolve and whitespace checks
pass. Runtime behavior is unchanged; no runtime test suite or paid experiments
were run. No performance/scientific parity is claimed.
