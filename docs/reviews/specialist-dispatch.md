# Specialist dispatch extraction review

Base: `2cf77f0`. Independent reviewer: `specialist_review` agent.

Result: approved, no correctness or scientific-behavior regressions found. Reviewed
tracked changes plus the new specialist module against the base. Verified ordering
(typed advice, inspection, advisory enrichment, coding/writing/review), supported-mode
and command precedence, model callback index/frontier/cache/accounting, conservative
inspection decisions, writer evidence merging, review checkpoints and pinned retrieval.
The dispatcher has explicit dependencies and no runner/private-method dependency.

Reviewer independently ran architecture, agents, agent specs, retrieval injection and
Laya tests: **80 passed**. A pytest-cache sandbox warning did not affect test results.
Nonblocking finding: documentation's bypass statement needed to explicitly exclude
typed advice. Resolved by documenting the dedicated advice path and demo disabled result.

## Attempts and evidence

- Baseline focused suites: 66 passed.
- Mechanical extraction with updated dependency patch locations: 66 passed; mypy passed.
- Added behavior fixtures initially failed because the scripted coding provider omitted
  a required action, then because the test used event `data` instead of `payload`.
  Corrected fixtures without weakening production validation; expanded suites: 80 passed.
- One unprivileged ruff invocation could not create its worktree cache. Reran with the
  worktree permission used for the other checks; lint passed.
- AgentRunner.run changed from 391 to 171 lines; agents.py from 776 to 539 lines.
  New specialists.py contains focused methods behind one dispatch operation. This is
  responsibility extraction, not a claim of net code reduction or research improvement.

No paid model calls or external research-backend deployment is part of this validation.

## Full-suite fixture correction

The first full run found six review-persistence failures. Two fixture patches still
replaced `autoresearch.agents.Literature` after fallback construction moved to the new
module. The offline HTTP guard rejected fallback retrieval; no external HTTP succeeded.
Updated those patch locations to `autoresearch.specialists.Literature`; no production
logic changed. Persistence, retrieval injection, architecture and agents then passed
56 tests. The independent reviewer approved the correction and separately reran all
six persistence cases: 6 passed. The final full run includes the corrected fixtures.

Static release checks passed: lint, formatting (142 files), types (76 source files),
AI specifications, browser suite (85 tests), public scanner and scanner self-test.
Synthetic demo completed with no error and retained the previous best after non-superior
meta-refinement. Wheel build succeeded; installed-package test passed. These are
software checks, not a research-quality or live upstream evaluation.

## Final release result

The first full run finished with 940 passed, 6 fixture failures and 3 skipped.
After correcting the two fixture patches, the complete fresh suite passed:
**946 passed, 3 skipped in 289.16 seconds**. Production source stayed fixed throughout
that final run. All reviewed behavior and release checks above remain satisfied.
Other worktrees were inventoried; unrelated source and documentation edits remain
untouched. The integration base is still clean `2cf77f0`.
