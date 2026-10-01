# Research process implementation review

Base: cdb5291. Independent reviewer: process_review, separate agent, read-only
review of backend commits and all frontend changes. Backend implementation was
performed by process_data in a separate managed worktree; the coordinator built
the frontend and performed browser acceptance. This is software evidence, not
scientific-quality validation.

## Findings and resolution

- P2: Graph and Temple could label blocked/waiting/exhausted runs Ready. Resolved:
  both consume the projected run status, with an explicit worker-error overlay.
  Regression covers blocked, waiting, exhausted, paused, pausing and terminal states.
- P2: Transient API errors could leave unchanged terminal runs displaying an error
  permanently. Resolved: invalidate the render signature and cancel animation on
  error. Regression verifies an identical successful snapshot redraws after recovery.

Reviewer independently reran all 7 process UI tests after fixes. Reviewed the final
backend delta for unique verification-start attribution, separate self-transition
visits, terminal timestamp ordering and model/agent metadata. Reviewed frontend
phase ordering independent of sorted archive keys and numbered visit labels.
Final reviewer conclusion: no remaining substantive findings or integration blockers.

## Validation evidence

- Full offline suite: 979 passed, 3 skipped (328.11 s). Started before the last three
  targeted backend regressions were added; final process suite separately: 9 passed.
- Existing web/accounting plus initial process integration: 90 passed.
- Final browser suites: 93 passed, including 7 process behavior checks.
- Ruff lint and formatting, mypy (82 source files), spec validation and public-file
  scanner passed. No dependencies added. CI now discovers all browser UI suites.
- Offline wheel built; installed-wheel behavior/asset/demo check: 1 passed (40.53 s).
- Full scripted demo completed: 140 model fixtures, 34 completed experiments.
- Actual browser: desktop cream/charcoal, 390px viewport; document width remains
  390px while graph and timeline have contained horizontal scrolling. Keyboard task
  selection, graph→trace→graph, selected-record inspection, phase inspection, active
  progression and checkpoint pause verified. Run selection retains original controls.
- Public synthetic screenshots in ../evidence/research-process/. No private data or
  live provider requests were used. Narrow/dark captures precede the final column-gap
  and panel-name refinement; light captures use the final implementation.

## Preserved limitations and unsuccessful attempts

Stage and run duration is wall time, including pauses. Missing call/SDK timestamps
remain unknown; no spans or allocation are fabricated. Model costs use configured
rates and exclude compute/storage. Unattributed legacy records stay visible.
An old synthetic fixture created before backend edits correctly refused execution
under the existing behavior-provenance guard. It was retained; a fresh fixture was
created on the final revision and verified running then paused. No guard was bypassed.
Initial local validation commands encountered sandbox cache/socket restrictions;
caches were redirected or the loopback validation command used normal escalation.
The first CLI server invocation used the wrong subcommand (`web`); corrected to
`serve`. These attempts made no scientific measurements or paid calls.
