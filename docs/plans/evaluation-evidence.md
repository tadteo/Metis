# Public-data evaluation integration

Plan: integrate the existing evaluation module as its own reviewed task on
codex/evaluation-evidence. Preserve registered task attempts, negative outcomes and explicit
unmeasured dimensions. Validate actual protected baseline execution on both public datasets,
resume without replay, failure denominators, and distinct model/retrieval variants. These are
small executable pipeline evaluations, not replacements for the paper's 107-task benchmark.

The module was developed in the concurrent pre-existing integration chat after the prototype
import. This task records its integration and validation honestly; it does not invent prior
feature history. Scope: evaluation module/tests/docs/public baseline evidence and evaluate CLI.

Prerequisite discovered by executing the real baselines: the protected evaluator needs the
formal experiment kind in its environment to distinguish subset and full protocols. Integrate
the concurrent executor's kind field and explicit SHA-256 manifest verification first, with
its seven mismatch/metadata/path/mount regressions. This preserves the stronger claim-evidence
receipt work already merged on this branch.
