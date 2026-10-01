# Research process and agent traces

Source: user approval of the temple-stage prototype and request to implement it.
Base: cdb5291. Implement on an isolated branch; retain the prototype separately.

Preserve the research page and controls. Add a phase/task graph in Overview, a
Temple broad-phase summary, and an Agent traces tab with expandable recorded work,
elapsed time, cost, and links between views. Use the archived workflow and durable
records. Never infer acceptance from execution, fabricate spans, distribute costs
without attribution, or discard failed attempts. Unknown timing/cost stays unknown.
Model cost is configured-rate accounting, not total compute billing.

Implementation: read-only run execution projection, browser graph/trace rendering,
shared existing Temple geometry; no scientific stage or budget behavior changes.
Update VIBE to record the explicitly approved use of Temple as a phase summary.

Acceptance: real stored attempts (including retries/failures), reconciled cost,
parallel overlapping calls, incomplete/legacy records, loops and skipped phases,
keyboard navigation and retained selection. Check both themes, desktop/narrow,
empty, paused, busy and failure states using public synthetic fixtures.

Validation: focused projection/API/browser tests, relevant repository checks,
independent review against base, fix findings, commit and merge only after passing.

## Completion evidence

Implemented authenticated read-only execution projection, archived-workflow graph,
Temple phase summary and hierarchical Agent traces. Each recorded passage keeps its
identity; calls/receipts expose measured or unavailable duration and attributed model
cost. UI supports both themes, narrow scrolling, keyboard inspection and safe polling.
VIBE, architecture and usage guide record the approved convention and limitations.

Independent review and full validation are in ../reviews/research-process.md. All
reported findings resolved. Final backend suite: 9 passed; browser suites: 93 passed;
full suite: 979 passed/3 skipped; installed-wheel check: 1 passed. No scientific
contracts changed. Full demo and browser validation remain explicitly synthetic.

Pre-integration inventory: main clean at cdb5291; unrelated modified worktrees
model-inventory, temple-refinement-review and temple-review preserved untouched.
Prototype branch 45659cd remains separate, with its preview available. Production
implementation is merged only after review, checks and this evidence are committed.
