# Independent review: writer recovery

Implementation branch: `codex/writer-recovery`, initially based on `0bdbd07`.
Committed foundation for the focused delta: `357d4a3`.
Reviewer: coordinating agent `/root`, independent of the implementation agent.
Scope: recovery delta relative to the frozen pending official worker integration;
`tests/test_writer_recovery.py`; task plan and retained failure evidence.

## Review outcome

The reviewer inspected stage validation, nested executor context propagation and exclusive
worker ownership and reported no blocking findings. A separate supervision task owns torn
JSONL-tail recovery at the parent boundary after worker exit is verified. Parent budget
reconciliation, asset provisioning and the initial upstream integration are separate changes.

## Evidence

- Before implementation, three deterministic regressions failed because swallowed transport
  failures incorrectly completed checkpoints.
- Ordinary environment: eight tests passed; one optional upstream smoke skipped.
- Pinned upstream SDK environment: all nine tests passed; the coordinator independently
  confirmed nine passed in 2.30 seconds.
- The upstream smoke imports the real `ContentRefinementAgent` from PaperOrchestra revision
  `ca1b3fa01c2970fc7cda32d16245db38d57b3f56`, renders a synthetic PDF with PyMuPDF, and uses
  the released prompts, retry loop and response parsing. Five denied requests remain in the
  receipt journal; checkpointing is rejected; the same stage completes after raising the
  test allowance and receiving one injected SDK response. HTTP send methods are disabled.
- Focused Ruff lint/format checks, strict worker typing and the public-file secret scan passed.

This verifies recovery behavior, not scientific writing quality or live provider performance.
No paid calls or real LaTeX compilation were performed. The older writer-interface test on the
initial branch is replaced by the separate official-writer integration.

## Commit ordering

The official integration foundation predates this recovery task and must be committed first.
Apply the focused recovery delta after that commit, with its tests, plan and this review.
Do not attribute the copied foundation to this task or reconstruct fictional history.
