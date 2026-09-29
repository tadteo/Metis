# Independent workflow review and validation

Date: 2026-09-29. Base: `9cd457d`. Branch: `codex/ai-workflow`.
Implementation commit: `78f9b49`. Independent reviewer: root coordinator, distinct
from the workflow implementer (`audit_science`).

## Reviewed implementation

The declarative ScientistTwo graph governs trusted handler dispatch, legal research
transitions, durable evidence postconditions, scientific stopping outcomes and explicit
operator intervention. Scientific handlers were extracted without removing seed,
subset/full, evolution, ablation, rebuttal, meta-review or final integrity loops.
Completed held-out evaluation prevents reopening the run for optimization.

The reviewer identified that caching `get_workflow()` concealed same-process edits
from behavior-provenance checks. The cache was removed and a content-change regression
added. The reviewer also requested rejection of duplicate JSON keys; loading now
rejects them, with a corresponding regression. The reviewer inspected these fixes and
handler extraction seams and reported an independent review pass before integration.

Validation after the fixes: 114 tests passed across `test_workflow.py`,
`test_fidelity.py`, `test_engine.py`, `test_coding.py`, `test_execution.py` and
`test_integrity.py`. Targeted mypy passed for seven workflow/engine source files.
Ruff, public-file scanning and `git diff --check` passed. Temporary extraction import
errors were caught by these suites and fixed before the passing run.

The inherited architectural writer test fixture returned a string where the official
writer now returns a tuple; the inherited TUI `action_quit` signature also failed
mypy. These unrelated failures were reported to the coordinator for integration fixes.
Passing software checks do not establish live scientific or reviewer quality.

## Follow-up findings under independent review

The coordinator subsequently found that workflow `agents` declarations could name
another valid catalog role while the trusted handler continued calling the original
role. Trusted action metadata now declares stage-role and specialist dependencies;
validation rejects discrepancies before run creation. Regression fixtures cover wrong
critic roles, omitted coding/review/integrity dependencies and duplicate role declarations.
This preserves the scientific roles and makes the inspected graph agree with dispatch.
Optional artifact-selector dependencies are included for limitation/planning producer
panels and final claim/held-out panels; no new calls are introduced. Optional advisory
services and native upstream endpoints remain declared through agent definitions.
The independent coordinator approved the metadata approach and these corrections.
After correction, 48 workflow/fidelity/engine tests and targeted mypy for six source
files passed; Ruff and whitespace checks passed.

A separate legacy-adoption safeguard inspects top-level work, coding/inspection/writer
journals and outstanding reservations, including zero-cost calls. It preserves every
journal and refuses to orphan incomplete work under newly adopted instructions.
Normal completed coding sessions retain their final finish proposal and remain eligible.
The independent reviewer requested actionable errors for malformed pending plan shapes and descriptor-safe parent traversal. Both were fixed, including a parent-symlink-swap regression. The focused legacy suite passed 26 cases; targeted mypy and Ruff passed. Commit: `b3db931`. Final independent review and
integration validation of these follow-ups are recorded by the coordinator.
