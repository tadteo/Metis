# Experiment history and interrupted execution

Status: implementation planned; independent review required before implementation commit.
Base: `6936a17` (honest existing-prototype import).

## Scope

1. Preserve rejected refinement hypotheses, parentage, measured results and comparison criticism in durable research history. Count them as attempted research, without making them selectable successes.
2. Persist a started execution marker before formal experiments and independent reproductions run. Recover durable receipts and scheduled jobs; retain unknown interrupted local outcomes as explicit failed records rather than replaying the same ID in a dirty workspace.
3. Retain initial peer review plus up to two rebuttal/revision cycles. ScientistTwo Table 5 distinguishes rounds 0/1/2; Appendix A.2's wording leaves invocation counting ambiguous. This is a documented interpretation, not recovered upstream code.
4. Assess mechanism-attribution enforcement within the ablation critic, adding it only if the existing contracts permit a focused, backwards-compatible implementation.

## Validation and review

Add regressions for rejected hypothesis preservation; crashes before result receipt; successful receipt reuse; Slurm reconciliation; reproduction interruption; and two complete rebuttal cycles. Run focused tests, lint, and relevant existing fidelity tests using the repository virtualenv with `PYTHONPATH=src`. Request an independent parent review of the diff and resolve findings before small Conventional Commits and merge.

## Sources

- [ScientistTwo §3.3–3.6, Table 5, Appendices A.2/B](https://arxiv.org/html/2609.19644v1): successful and failed traces inform evolution; comparison protects incumbents; review/rebuttal recurs; ablations must attribute gains to the proposed mechanism.
- Existing `docs/paper-spec.md`, `docs/fidelity.md`, and `src/autoresearch/coding.py` provide the repository stage contracts and interrupted-command precedent.

## Ownership

This task owns `src/autoresearch/engine.py` and focused tests/docs. The integrity implementation is reviewed separately. No changes to the original checkout; all implementation stays on `codex/experiment-history` until reviewed.

## Implementation decisions

- `peer_rounds` counts completed rebuttal/revision cycles after the initial review. The default 2 therefore permits three reviewer invocations. This follows Table 5 round 0/1/2 while documenting Appendix A.2's ambiguous wording.
- `result_preference=scientific_critic` requires every registered metric and at least one measured gain; independent critic acceptance still determines whether tradeoffs constitute improvement. `pareto` additionally forbids any regression and requires primary-metric gain. Neither policy is a published numerical utility function or a significance test.
- Rejected refinements retain a distinct hypothesis ID, parents, measured workspace, producing experiment IDs, criticism and terminal status. Pending comparison attempts are counted but cannot be selected as successful.
- Every execution writes host-owned start intent before launch. A result receipt wins on recovery. Pending scheduler IDs are polled; saved Slurm submission records are reconciled by the executor. An unreceipted local/Docker execution is recorded as `failed` with `failure_kind=interrupted_unknown_outcome`, separately from scientific rejection. Its workspace is retained and never replayed under the same ID.
- Live ablation acceptance requires the independent critic's explicit attribution assessment and completed ablation references for the selected method. Generic-control-only gains and stale/unknown references cannot pass. Failed refinement returns to the critic; exhausted unresolved attribution terminates as failed research, preserving all evidence.

## Validation evidence

- `PYTHONPATH=src pytest -q tests/test_experiment_history.py tests/test_fidelity.py tests/test_engine.py`: **39 passed** in 22.02 seconds.
- `ruff check --no-cache` on the changed engine/tests: passed.
- `mypy src/autoresearch/engine.py --follow-imports=silent`: passed.
- Parent independent review requested before implementation commits. Review feedback already incorporated: preserve producing experiment IDs; reject a refinement sharing the incumbent ID; never resubmit uncertain scheduler work; reassess ablations after a rejected refinement.
- Cross-branch analysis metadata wiring is prepared separately for integration after the integrity helper/configuration change; it is not part of this branch's validated code yet.

## Independent review

Reviewer: root agent, separate from the implementation agent. Review approved the complete diff subject to checking every accepting panel member's ablation evidence; that finding is fixed and has regressions for missing, contradictory and unknown-source assessments. No implementation was committed before this review. The 2026-09-29 review also confirmed the preserved prior-best meta fallback and the explicit ablation re-entry on a non-superior refinement.
