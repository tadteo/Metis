# Fidelity report and integration status

This repository is a **paper-guided implementation, not a validated capability reproduction**. The orchestration preserves the intended research stages, while several important upstream capabilities are reconstructed or have narrower implementations. Treat this report as part of the public interface, not as optional fine print.

The [primary-source specification](paper-spec.md) lists the published behavior, numerical limits and unresolved details. This report describes implementation choices and remaining evidence requirements. Review date: 2026-09-29.

## Implemented structure

The stage enum and engine explicitly represent limitation verification, seed generation, novelty/filtering, baseline reproduction, subset/full execution and engineering, history-based evolution, selection, ablation planning/execution/refinement, comparison, drafting, peer review, experimental rebuttal, revision, meta-review/refinement and integrity. These are separate checkpointed stages with observable transitions. Rejected candidates and experiment records remain in research memory.

The default scientific limits follow the reported settings where numerical values are public. Initialization uses two seeds, followed by one evolved idea and one unused seed in subsequent rounds. The seed pool defaults to eight, which is a local assumption, not a reported upstream value. Review permits an initial review plus two rebuttal/revision cycles. The writer uses three reflection rounds by default, a local reconstruction assumption independent of the paper's peer-review limit. Structured decisions use `accept/refine/reject` rather than the paper's stage-specific vocabulary.

## Deviations and current limitations

| Area | Current implementation | Fidelity consequence |
|---|---|---|
| Model backbone | xAI-compatible general model, configurable cheap and frontier providers | User-requested departure from the reported Gemini/Claude configuration. Quality parity is unmeasured. |
| Original prompts | Repository-authored role prompts and schema | Upstream ScientistTwo prompts were not located; exact prompt fidelity is not claimed. |
| Coding runtime | Structured file edits and executable argument vectors | Replaces the reported Claude Code agent harness; multi-step coding skill depends on the configured model and refinement loop. |
| Literature | Crossref metadata search plus supplied references | Replaces Google Search. Metadata coverage is narrower than reading and interrogating full papers; two retrieved references do not establish exhaustive novelty. |
| Writer | Reconstructed outline, literature, parallel section writing, figure planning, synthesis and reflection/repair | Preserves specialist decomposition but does not run upstream PaperOrchestra. Figure planning is not a general plotting/illustration agent; outputs are Markdown, without guaranteed conference LaTeX/PDF. |
| Reviewer | Reconstructed summary, literature/expansion, historian, baseline scout, novelty/technical question answering and final reviewer panels | Follows the published subsystem topology with local prompts and Crossref retrieval. Search coverage, publication cutoffs and scores are not validated as equivalent to ScholarPeer. |
| Result preference | All configured metrics must not regress; primary metric must strictly exceed the declared margin | A transparent local numerical interpretation of an unspecified multi-metric preference function. It is not a significance test or a general scientific utility function. |
| Repeated seeds | Seed-level experiment results are retained and aggregate metrics drive comparisons | Do not infer calibrated uncertainty or statistical significance merely because several seeds ran. |
| Integrity | Experiment-time model audit, independent reruns of every selected main-result seed, citation metadata re-retrieval and final model audit | Historical ablation/rebuttal results are retained but not all independently rerun at finalization. Metadata existence does not prove citation support. Complete CoE audit parity is unverified. |
| Source visibility | Bounded source snapshots and prompt context | Projects exceeding configured/source-context bounds require a narrower adapter; this is not an unrestricted repository coding agent. |
| Agent ensembles | Configurable panels, conservative verdicts, optional escalation | Additional implementation policy; effects on quality, correlation and cost are unvalidated. |
| Runtime and UI | SQLite checkpoints, local console, cost reservations, Docker/local/Slurm executors | Engineering extensions. Their presence is not evidence of scientific success. |
| Offline demonstration | Scripted agents and an executed synthetic polynomial-regression benchmark | Validates plumbing and control flow, not autonomous reasoning, novelty or publication readiness. |

The [paper-spec assumption ledger](paper-spec.md#assumptions-and-meaningful-deviations) distinguishes unpublished information from deliberate changes. Operational budgets stop or pause work honestly; they must not be described as having satisfied scientific acceptance criteria.

## PaperOrchestra: actual public integration surface

The authors publish [google-research/paper-orchestra](https://github.com/google-research/paper-orchestra). Its documented Python CLI accepts `--raw_materials_dir`, `--latex_template_dir` and `--output_dir`, with optional plotting and writer/reflection model settings. The source entry point is [paper_writing_cli.py](https://github.com/google-research/paper-orchestra/blob/main/paper_writing_cli.py). It expects filesystem materials and its own environment, rather than this repository's JSON role protocol.

**Current status: not integrated.** `role_commands` is a generic extension mechanism, not an installed PaperOrchestra backend. A proper wrapper must:

1. Materialize a private raw-material directory from the selected hypothesis, full results, ablations and evidence, retaining artifact identifiers.
2. Invoke a pinned upstream revision in its required environment with a validated conference template and private output directory.
3. Capture the produced source, figures, bibliography, compile diagnostics and final document as versioned artifacts.
4. Map a returned manuscript and provenance to `AgentResponse`, including subordinate model usage. Preserve upstream failure and incomplete-output states.
5. Handle execution longer than the current role-command timeout through a resumable integration, rather than pretending the process completed.

Those wrapper steps are a proposed integration design, not copied upstream implementation. A completed bridge still needs a representative writing evaluation before claiming parity with the component used by ScientistTwo.

## ScholarPeer: published design, unverified callable release

The [ScholarPeer v2 paper](https://arxiv.org/html/2601.22638v2) describes structured paper extraction; search and literature expansion; a domain historian; a baseline scout; novelty/technical question answering; and review synthesis. Appendix G publishes its agent prompt templates. The inspected arXiv entry and [Google Research publication page](https://research.google/pubs/scholarpeer-a-multi-agent-framework-for-automated-peer-review/) did not expose an official callable repository or hosted API.

**Current status: a local reconstruction of the published review topology.** No `scholarpeer` package, endpoint or CLI name is assumed to exist. This repository uses original prompts, Crossref metadata and its own structured output contract. A future upstream integration should use a verified release if available; otherwise improvements to the reconstruction remain explicitly independent. It should record the publication cutoff, retrieved literature, missing-baseline findings, question/answer evidence, guidelines and final review separately. The final score mapping must match the intended venue grading rubric; a review-quality benchmark score is not automatically an acceptance score.

`role_commands.peer_review` can point to a user-owned wrapper returning the local JSON contract once such an integration is built. Configuration alone does not install or validate an upstream implementation. Keep held-out evaluation separate from the reviewer used to improve drafts.

## Evidence required for stronger claims

Control-flow tests should cover stage limits, rejection, evidence-preserving failure, non-improving refinement, renewed ablations after method changes, experimental rebuttal and resumption. A passing suite demonstrates these software properties only.

Scientific validation requires real public tasks, fixed protocols, reproducible code, reported negative results, independent review, complete attempted-task denominators and full cost accounting. Compare model routing, retrieval, writer/reviewer substitutions and audit scope as separate ablations. Until those measurements exist, do not claim comparable research capability, publication readiness, reward-hacking resistance or the paper's reported success rate.

Additional execution repairs: failed baseline, ablation and rebuttal subprocesses receive
bounded coding repairs (using the configured engineering limit). Exhausted supplementary
repairs block advancement rather than allowing missing measurements to appear as
completed controls. This is an explicit operational safeguard, not a reported extra
ScientistTwo scientific iteration. A configured baseline command is authoritative.
