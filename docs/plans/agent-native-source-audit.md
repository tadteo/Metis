# Agent-native entry: primary-source audit

Evidence checked: 2026-09-30. Base: `8dbc4ac`. Scope: planning only; no runtime changes.

## Task plan and boundary

Audit published ScientistTwo inputs, experimental responsibilities, stage transitions and
configuration before proposing simpler Metis onboarding. Own only this document. Preserve
existing scientific contracts unless a separately identified source correction is needed.
Acceptance: primary links, explicit unknowns, scientific-versus-product distinctions and
reviewable implications. Validation: source inspection, link inspection and `git diff --check`;
no executable behavior changes. Independent review and integration belong to the coordinator.

## Published scientific contract

ScientistTwo accepts a problem; benchmark tasks use accepted papers’ problem specifications
and codebases (§4.1). Exact launch packaging is unspecified. Baseline coding reproduces subset experiments. Subset critics compare reproduced
measurements; full-set critics compare original SOTA results. Decisions are Good, Bad or
Engineer. Selection uses full-set successes. Evolution retains successful and failed traces.
Ablation and meta-refinement replace incumbents only after independent strict-improvement
comparison; accepted replacements repeat downstream analysis. ScholarPeer drives experimental
rebuttal; Stanford review remains held out. There is no predefined numerical target, but
protocol changes are forbidden. [Paper §§3–4, Appendix B](https://arxiv.org/html/2609.19644v1#S3)

Published limits: limitation rounds 16; novelty references 2 through Google Search; experiment rounds 4; candidates
one seed plus one evolved; successful ideas 4; engineering rounds 2; ablation refinement 1;
peer rounds 2; acceptance score 8; review-driven refinement 1. Seed-pool size, round-zero
interpretation, review-cycle counting and metric aggregation are not completely specified.
[Appendix A.2](https://arxiv.org/html/2609.19644v1#A1.SS2)

Table 5 reports held-out acceptance 49.0%, 73.5%, 69.4% across zero/one/two rebuttal-enabled
cycles: benefit is not monotonic. These ablations do not establish that every architectural
change reduces performance. [§4.2](https://arxiv.org/html/2609.19644v1#S4.SS2)

## What agent autonomy does and does not mean

The official project describes coding agents producing self-contained reproducible scripts.
It also describes an experiment-time filter for rule violations, a bibliography repair
agent, and a code audit feeding manuscript corrections. The post-hoc audit checks numerical
reproduction, specification compliance, reference existence and method/code agreement.
Thus the published system combines agent authorship with verification: generated scripts
are legitimate research artifacts, not evidence that humans must supply launch commands.
[Official project, Integrity](https://scientist-two.github.io/#integrity)

At this inspection, the official GitHub profile listed one repository, its website. This
bounded check did not locate a runnable ScientistTwo orchestrator, complete initial prompt,
user input schema or exact agent prompt pack. Do not label a local implementation “exactly
the same” as unpublished internals. [Official GitHub account](https://github.com/scientist-two)

## Implications for the Metis plan (recommendations, not upstream claims)

1. Add a thin initial pipeline agent that resolves the user's objective and optional papers,
   code or data into sourced research context. It can search for missing references, inspect
   an existing project or initialize a new workspace. It must not require the user to choose
   an internal setup mode. Charge retrieval, reasoning and execution to the same project
   ledger as subsequent scientific stages.
2. Keep that entry adapter separate from the paper's scientific stages. Its completion means
   the task is sufficiently understood to start limitation extraction; it does not certify
   reproducibility, baseline success or a scientific contribution. Existing code is material
   to inspect, not permission to skip novelty, baseline or scientific review.
3. Let baseline and experiment coding agents author and repair commands, environments,
   adapters and measurement extraction. Preserve source revisions and executable receipts.
   Removing command fields from the user form is insufficient if downstream creation still
   requires those commands before any agent can run.
4. Resolve benchmark datasets, metrics, comparison results and task restrictions from
   sources. Record unavailable values honestly. Preserve a stable comparison contract once
   established; generation freedom must not permit changing the yardstick after seeing a
   candidate's results. Immutable protocol storage is a local enforcement mechanism, not a
   reason to require humans to write evaluator paths.
5. Keep separate baseline-reproduction evidence, subset decisions, full-benchmark decisions,
   methodological attribution and manuscript judgments. Avoid collapsing them into one
   scalar target or allowing a language model's metric assertion to stand in for execution.
6. Do not introduce additional user budget forms or new scientific stopping policies under
   the label of simplification. Keep existing paper-aligned defaults and the documented
   ambiguities in [paper-spec.md](../paper-spec.md). In particular, its seed count of eight,
   initial count of two and interpretation of peer rounds are local assumptions.
7. Retain all current downstream loops as explicit acceptance criteria for the refactor.
   Distinguish intake/ownership changes from any scientific behavior changes in validation.
   An objective with no identifiable reference context is an extension beyond the demonstrated
   paper-and-codebase benchmark; discovery may clarify it, but should not fabricate comparators.

8. Audit actual configured defaults against this source ledger before implementation. A
   discrepancy is a separately recorded reconciliation, not authorization to silently alter
   novelty policy or scientific iteration limits during an onboarding refactor.

## Completion evidence and remaining uncertainty

Read the primary paper, configuration and ablation sections; inspected the project integrity
claims and official repository listing; cross-checked the existing Metis paper-spec ledger.
No paid research run, performance comparison or fidelity-equivalence claim is made.
The proposed intake agent and shared-budget policy are Metis design choices requested by the
user. Their usability benefits and scientific performance require subsequent validation.

Independent review: coordinator `/root` checked this audit against the primary paper
passages and approved it for planning with no blockers. Its precision finding—identify
Google Search as the published novelty retrieval provider—was incorporated before commit.
