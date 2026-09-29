# Metis research contracts and paper inspiration

Evidence reviewed: **2026-09-29**. Metis is an independent research platform inspired by and extending ScientistTwo. This document traces paper-derived contracts and defaults alongside Metis design choices; it does not make replication the project's identity or claim equivalent scientific performance.

## Evidence and release boundary

The cited paper version for these research foundations is [Nam et al., arXiv:2609.19644v1](https://arxiv.org/abs/2609.19644v1), submitted 2026-09-17. The full paper, including appendices, is [available as HTML](https://arxiv.org/html/2609.19644v1). Section links below identify the relevant behavioral specification. The paper is marked CC BY 4.0; the descriptions here are independently written, rather than copied prompts or manuscript text.

The [official project](https://scientist-two.github.io/) provides the paper, generated manuscripts, demo and results. The [official GitHub account](https://github.com/scientist-two) listed one public repository at inspection: [the project website](https://github.com/scientist-two/scientist-two.github.io), whose top level contains `generated-papers`, `static`, `index.html` and a license. No official executable ScientistTwo orchestration implementation or exact agent prompt pack was located in these sources. That is a bounded release audit, not proof that no other release exists.

## Published configuration

These values come from [Appendix A.2](https://arxiv.org/html/2609.19644v1#A1.SS2). They are scientific iteration limits, distinct from infrastructure retries, spending limits and pause/resume controls.

| Parameter | Reported value |
|---|---:|
| Limitation verification rounds | 16 maximum |
| Novelty references retrieved | 2, through Google Search |
| Experimentation rounds | 4 maximum |
| Candidates per round | 1 seed + 1 evolved |
| Successful idea stopping target | 4 |
| Engineering refinements | 2 maximum |
| Ablation refinements | 1 maximum |
| Peer-review assessments including initial | 2 by default; configurable |
| Experimental rebuttal/revision cycles | 1 by default; `peer_rounds=3` allows 2 |
| Review acceptance threshold | 8/10 |
| Meta-review idea refinements | 1 maximum |

Review-budget interpretation: `peer_rounds` counts total assessments including the initial review. The existing default of two assessments permits one experimental rebuttal/revision cycle; setting three permits both cycles illustrated by Table 5 and is regression-tested with real supplementary experiment fixtures. Appendix A.2 limits peer review to two rounds and refinement to once, while Table 5 labels zero, one and two rebuttal-enabled cycles. This explicit local interpretation preserves existing configuration and spending semantics; it does not claim uniquely recovered private orchestration.

Reported agents use Gemini 3.6 Flash, except coding, ablation, rebuttal and draft enhancement use Claude Code with Opus 4.8. Initial drafting incorporates PaperOrchestra and ICLR 2025 formatting; review uses ScholarPeer. The Stanford Agentic Reviewer is a held-out evaluator, not an optimization target. [Sections 3.5–4 and Appendix A.2](https://arxiv.org/html/2609.19644v1#S3.SS5)

## Executable stage contracts

The following contracts define the current Metis research loop, drawing on the cited paper. They can evolve through documented design changes and validation. Identifiers, schemas, persistence, failure labels and agent interfaces are design choices for this repository. They must not be mistaken for recovered upstream source code. Numeric limits are the published values above unless explicitly overridden.

| Stage and evidence locator | Input and required output | Required transition behavior |
|---|---|---|
| Limitation extraction, [§3.1](https://arxiv.org/html/2609.19644v1#S3.SS1) | Problem, reference method, sources → limitations with evidence and a mechanism that could be improved | Run a separate verifier; send missing issues back to extraction. Preserve earlier limitations and verifier feedback. |
| Limitation verification | Limitations → `accept`, `refine`, or `reject`, reasons and missing coverage | Bound the loop independently of seed generation. Exhaustion must not silently imply successful verification. |
| Seed generation | Verified limitations and existing ideas → distinct hypotheses | Preserve the seed pool and relationships to limitations. Generation must be iterative and aware of previous candidates. |
| Novelty checking | Hypothesis, retrieved references → comparative novelty assessment | Store retrieved references and retrieval provenance. Rank the completed seed pool; do not allow a self-declared novelty claim to substitute for literature evidence. |
| Baseline reproduction, [§3.2](https://arxiv.org/html/2609.19644v1#S3.SS2) | Reference code, fixed subset protocol → executable baseline, logs and measured results | Subset comparisons use reproduced baseline measurements. A command plan alone is not reproduction. |
| Subset implementation | Idea and baseline implementation → changed code, actual experiment outputs | Run specification validation after execution; route outputs to an independent subset critic. |
| Subset criticism | Comparable subset results → `good`, `bad`, or `engineer`, with reasons | `good` permits full evaluation; `bad` prunes the idea while preserving history; `engineer` requests concrete engineering changes. |
| Subset engineering | Criticism, idea and code → revision plus fresh experiment results | Re-enter subset criticism. Bound refinements; exhaustion without `good` prunes. Count scientific refinements separately from fixing a transient executor failure. |
| Full implementation | Subset success and complete benchmark protocol → full benchmark results | Cover the registered datasets and metrics. Preserve the published reference results as the full benchmark comparator. |
| Full criticism / engineering | Full results → decision and optional refinement instructions | Keep this distinct from subset criticism. A subset success is not a successful research candidate. Only validated full results can enter the successful candidate set. |
| Idea evolution, [§3.3](https://arxiv.org/html/2609.19644v1#S3.SS3) | Complete accumulated successful and failed traces → evolved hypotheses | Mix evolved hypotheses with unused seeds in novelty order. Evaluate every new hypothesis through the same subset-to-full path. |
| Candidate selection | Full benchmark successes and their evidence → selected candidate and rationale | Compare across candidates; keep provenance for the choice. When the round limit is reached with no successes, terminate as unsuccessful research. |
| Ablation planning/execution, [§3.4](https://arxiv.org/html/2609.19644v1#S3.SS4) | Selected implementation → component interventions and measured outcomes | Execute every approved ablation. A prose prediction of the effect is not an ablation result. |
| Ablation criticism | Component results → `good` or `refine` | Criticism may request structural method changes, not only better exposition. Route requested changes through full engineering. |
| Result comparison | Incumbent and proposed complete results → strict improvement decision | Replace the incumbent only after this independent comparison accepts the new evidence. Keep the original intact until then. |
| Ablation re-entry | Accepted new implementation → new component plans/results | Recompute ablations when the method changes; do not reuse stale claims about an earlier implementation. |
| Initial manuscript, [§3.5](https://arxiv.org/html/2609.19644v1#S3.SS5) | Selected idea, main results, ablations → manuscript with traceable claims | Include full methods, limitations and evaluation context. Every reported result must identify the producing artifact. |
| Peer review | Current manuscript and available evidence → strengths, weaknesses, questions, score | Keep reviewer state separate from the writer. Below-threshold reviews trigger experimental rebuttal. |
| Rebuttal planning/execution | Reviewer concerns → supplementary tasks, actual code and results | Preserve the question-to-task-to-result mapping. Editing the manuscript alone cannot discharge an empirical concern. |
| Manuscript enhancement | Review, rebuttal evidence and previous draft → revised draft | Re-enter peer review. Maintain draft versions and a response describing which concerns remain unresolved. |
| Meta-review, [§3.6](https://arxiv.org/html/2609.19644v1#S3.SS6) | Revised manuscript plus peer review → `accept` or `refine` and strategic critique | Acceptance finalizes subject to integrity checks. Refinement reopens the method through full engineering and independent comparison. |
| Meta-refinement feedback | Proposed improved method → comparison and downstream reruns | Improvement returns to ablations, drafting and peer review. A non-improving proposal is discarded and the prior best outputs retained; this is a completed fallback, not a fabricated acceptance. |

The generic critic/refiner abstraction in Figure 4 is useful for implementation, but does not justify merging these scientific stages. Each invocation requires its own role, input snapshot, verdict, feedback, iteration identity and provenance.

## Memory and evidence model

An execution trace should contain the hypothesis, measurements, code revision, terminal decision and explanatory criticism. Evolution needs all prior rounds, including diagnostic failures; selection needs all full benchmark successes. This requirement follows the trace aggregation in [§3.3](https://arxiv.org/html/2609.19644v1#S3.SS3).

For this implementation, the recommended durable representation is an append-only event journal plus versioned artifacts. An idea has parent identifiers and a source (`seed`, `evolved`, `ablation`, `meta_review`). An experiment references immutable code, dataset protocol, command, environment, seeds and metric definitions. Failures must distinguish scientific rejection, invalid specification, invalid output, infrastructure error and cancellation. These storage schemas and labels are local engineering decisions.

Summarization can help context management, but a summary should carry artifact identifiers and access to the underlying trace. Dropping failed experiments to reduce context is an unvalidated fidelity reduction. Reviewer identities, sampling settings and disagreement records belong in the trace when ensembles are used. Agent count is configurable; multiple agents must aggregate through a recorded rule rather than silently choosing an output.

## Integrity gates

The [official project integrity description](https://scientist-two.github.io/#integrity) identifies four checks: reproducible numerical results, compliance with task rules, real references and agreement between written methods and implemented code. Its refinement mechanisms include an experiment-time specification filter, search-grounded bibliography repair and a code audit that feeds corrections to the writer. Reproducible scripts are required during experimentation, rather than retrofitted after manuscript completion.

The implementation should give these mechanisms separate durable outcomes:

1. **Specification compliance:** evaluate immutable task restrictions after each experiment. Reject rule violations and reward hacking even if numerical scores improve. The actor that wrote code cannot authorize changes to the benchmark protocol.
2. **Score reproduction:** rerun the archived implementation using an independently recorded command and compare measurements under configured tolerances. An asserted score in model output is never an observation.
3. **Reference existence and support:** resolve references through a literature provider, store source identifiers, and make the writer repair incorrect bibliography entries. Existence alone does not establish that the reference supports the claim.
4. **Method/code alignment:** compare manuscript claims with the archived implementation. Record discrepancies and rerun the check after correction.

The extra distinction between citation existence and claim support, immutable protocols, explicit unknown outcomes and tolerance configuration are local safeguards. A missing retrieval backend or failed rerun means the relevant check is unverified, not passed.

## Why the loops are retained

The paper's [ablation section](https://arxiv.org/html/2609.19644v1#S4.SS2) reports effects of idea evolution, review/rebuttal, meta-review refinement and integrity repairs. These are empirical findings from the authors' benchmark, not guarantees for this implementation.

| Evidence | Reported observation | Implementation implication |
|---|---|---|
| Figure 10 | Evolved ideas increasingly supply the selected candidates | Preserve evolution and failed traces; do not stop after the first viable seed. |
| Table 5, zero / one / two rebuttal-enabled cycles | ScholarPeer ratings 5.2 / 6.9 / 7.6; acceptance 46.9% / 79.6% / 93.9% | Preserve experimental rebuttal and repeated review. |
| Table 5, held-out reviewer | Acceptance 49.0% / 73.5% / 69.4% | Do not infer monotonic real-world quality from the in-loop review score. |
| Table 6, meta-refinement case | Overall metric 0.897 → 0.916 | Preserve the path from manuscript criticism back to method experiments. |
| Official project integrity table | Full repairs: 49/49 score verification, 0/49 spec violations, 0/1814 false references, 49/49 method/code agreement | Test all four checks independently; pipeline completion alone is insufficient. |

The [project](https://scientist-two.github.io/) reports 86 successful tasks from 107 and automated review outcomes. A replication must report the denominator including failures and distinguish automated acceptance from acceptance at a human-reviewed venue. No capability parity claim is justified by a mock run or a passing software test suite.

## Assumptions and meaningful deviations

Keep this ledger synchronized with implementation changes. An extension preserves all original stages; a replacement changes a scientific capability and requires validation.

| ID | Unpublished detail or deliberate change | Required disclosure / handling |
|---|---|---|
| A01 | Exact ScientistTwo prompts were not located | Repository prompts are reconstructions. Version and persist them; never label them upstream prompts. |
| A02 | Seed pool size, initial candidate count and exact generation retry rules are unspecified | Defaults `seed_count=8` and `initial_candidates=2` are local assumptions. Expose these as configuration and record resolved values in each run. |
| A03 | §3.3 starts with seed-only round zero; Appendix A.2 describes one seed plus one evolved candidate per round | Use a documented initialization interpretation, preferably two seed candidates initially followed by one unused seed plus one evolved candidate. Do not represent that interpretation as an unambiguous paper value. |
| A04 | Table 5 reports zero, one and two rebuttal-enabled cycles; Appendix A.2 uses ambiguous round/refinement wording | Preserve `peer_rounds` as total assessments, default two; configure three for two experimental rebuttal/revision cycles. Test both cycles and disclose this counting interpretation. See the architecture reconciliation plan. |
| A05 | Ablation and rebuttal task counts are symbolic, not fixed in the public configuration | Let planners choose substantive tasks, subject to an explicit declared ceiling. Empty plans cannot silently pass a requested empirical investigation. |
| A06 | Multi-metric preference and strict improvement formulas are unspecified | Register dataset/metric directions and scientific tolerances; use a separate comparison role. Disclose the comparison policy and uncertainty. |
| A07 | Representative subset construction, random seeds and exact stopping thresholds for scientific effect sizes are unspecified | Require project-level benchmark adapters and provenance; never optimize the evaluation protocol in response to candidate results. |
| A08 | Detailed behavior at every exhausted verifier/ablation budget is incompletely specified | Fail closed or retain an explicitly unresolved best output; do not convert exhaustion to approval. |
| D01 | User requests Grok default, compatible APIs, OpenRouter and cheap/local routing | Intentional model/backbone deviation from the authors' configuration. Evaluate model routing separately from stage fidelity. No evidence yet establishes equal scientific performance. |
| D02 | Iterative tool-using coding harness substitutes for the reported Claude Code runtime | Repository exploration, multi-file edits, commands, debugging, bounded retries, clean export, checkpointed observations and diffs are implemented. Comparative capability remains unmeasured. |
| D03 | Official PaperOrchestra integrated; ScholarPeer reconstructed from released Appendix G | Pin official writer source/templates; retain native grounded search, reflection, plotting, usage and compilation. ScholarPeer lacks a callable release in checked primary sources; exact published prompts and decomposition are implemented. |
| D04 | Literature search may use another provider or a curated corpus | Google Search substitution. Record query, retrieved sources, timestamp and coverage limitations; an offline empty search must not certify novelty. |
| D05 | TUI, CLI, durable checkpoints, Slurm, privacy controls, budgets and provenance | User-requested engineering extensions, not claims about the original implementation. Budget exhaustion pauses or terminates honestly without skipping scientific stages. |
| D06 | Demonstration provider and synthetic experiments | Software demonstrations only. Clearly mark all generated evidence as synthetic and prevent it from being presented as real research. |
| D07 | Configurable ensembles, cheap-agent routing and escalation | Extensions whose quality/cost effects require evaluation. Preserve separate producer and critic invocations even when using the same model endpoint. |
| D08 | Strict machine-readable artifact schemas and security validation | Local engineering decisions. Reject malformed plans rather than guessing an executable command or accepting unsupported metrics. |

The upstream component references are [PaperOrchestra, arXiv:2604.05018](https://arxiv.org/abs/2604.05018) and [ScholarPeer, arXiv:2601.22638](https://arxiv.org/abs/2601.22638). See the executable integration and prompt provenance in [PaperOrchestra](paper-orchestra.md) and [ScholarPeer](scholarpeer.md).

## Scientific validation plan

Software validation should exercise both happy paths and the scientifically important adverse paths: every refinement loop, exhausted engineering, no-success termination, rejected replacement, stale ablations after an improved method, below-threshold review, meta-review re-entry, invalid specification, unresolved citations and resumption after interrupted experiments. Synthetic fixtures can establish these control-flow properties only.

A research capability evaluation must subsequently run reproducible public tasks with real models and compute, log every attempt, retain held-out evaluation, compare baselines under fixed protocols and measure both cost and failure rate. Changing model providers, reviewer implementation, retrieval or stopping limits should be assessed as separate ablations. Until that evidence exists, describe Metis as an independent, paper-inspired research platform with explicitly documented extensions and unmeasured scientific performance.
