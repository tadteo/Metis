# Stage exit reports

Source: user requests a report after every stage, accessible from the main Metis interface.
Base: 236da46. Isolated branch: codex/stage-reports.

Save a deterministic, private report atomically with each attempted stage checkpoint,
including failures, budget stops and pending work. Preserve repeated visits. Use recorded
state changes and decisions, never a new model call or inferred scientific acceptance.
Reports identify the attempted stage, checkpoint, status, new observations/evidence,
recorded feedback and next stage. Unchanged historical feedback is not new evidence.
No retroactive invented reports for older runs; existing activity remains accessible.

GUI journey: Research → Stage reports → select an attempt → read observations and
expand evidence; return to Activity or Manuscript for original traces/files. Reuse
existing responsive split panel, typography and safe text rendering. Preserve selection
and keyboard focus during polling. CLI/TUI keep access through existing event inspection.

Validate atomic persistence, retries/failures, redaction, unchanged-feedback exclusion,
legacy empty states and authenticated read access. Run focused and repository checks;
inspect synthetic desktop/narrow, light/dark and keyboard selection. Obtain independent
review before commit/merge, update fidelity evidence with the actual implementation SHA.

## Implementation and review

Reports are private `stage_report` events, atomically appended with the outcome and
checkpoint. Engine-step entry snapshots preserve changes across internal saves.
The authenticated run detail supplies the main Research → Stage reports reader.
No model calls, dependencies, scientific route changes or retroactive reports added.
Independent review approved after fixing internal-save evidence loss, manuscript
identity, pending reasons and detail focus during polling; see ../reviews/stage-reports.md.

During implementation main advanced through execution-options and blocked-run recovery
changes (804c33b). Integrate these without overwriting their controls, text or tests.
All other managed worktrees remain untouched.

Acceptance before integration: full suite 1038 passed / 3 skipped; browser suites
99 passed; installed wheel 1 passed; synthetic demo completed; all static, schema
and public-file checks passed. No paid/live research evaluation was performed.

Implementation commit: c027069. Main integrated through d0e2fd8 in 228639c, retaining
both append-only documentation/test conflicts. Final integration evidence: 98 backend
checks, 102 browser checks, 17 fidelity checks, static checks and independent integration
review passed. Pre-merge inventory found main clean and unrelated metered-experiments
worktree edits; those edits were left untouched. Source implementation, review,
synthetic screenshots and fidelity provenance are committed before merging to main.
