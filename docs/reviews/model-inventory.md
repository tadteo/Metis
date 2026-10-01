# Model inventory independent review

Base: cdb5291. Implementation branch: codex/model-inventory.
Reviewer: separate agent `/root/review_prototype` (read-only review and isolated-store
reproductions); implementation, tests and docs by the primary agent.

Findings resolved:
- Normal new inquiry Next failed to advance to Review; fixed and browser regression.
- Fresh project inventory pinned future global additions; moved defaults into inherited
  values and added a global-addition regression.
- Key-save retry duplicated an Add model entry; stable draft ID and retry regression.
- Closing modal retained unsaved passwords; close clearing and regression.
- Project allowlist could be supplied without inventory; reject before new-run creation.
- Native writer model-name aliases could authorize a different endpoint; require exact
  native Google endpoint/key identity and guard the actual writer entry point.
- Old workspace missing fields masked inherited inventory; preserve raw-field semantics.
- Legacy global rows accidentally enabled inventory; explicitly preserve old routing
  locally and in remote snapshots, with a regression.
- Advanced primary changes were silently replaced; saved explicit edits turn inventory
  off, conflicting direct file identity is rejected, compact edits synchronize primary.

Final independent verdict: approved, no remaining blocking findings, contingent on
validation. No source edits by reviewer. Software validation and synthetic screenshots
are recorded in the task plan. Paid access, automatic quality equivalence, cost savings
and live SSH deployment are not established by these checks.

Integration re-review approved after main cab845a: both features retained, script order
temple → process → app → model-inventory, both stylesheet sections and web routes
present, no conflict markers. Integrated validation: 997 Python passed / 3 skipped,
98 browser passed, types/lint/format/package/scanner passed. Three skips require
optional installed-wheel or upstream writer prerequisites; wheel was tested separately.
