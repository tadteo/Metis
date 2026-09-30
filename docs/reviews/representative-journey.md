# Representative journey diagnostic review

Base: `67e70a9`. Scope: task plan and public Markdown/JSON evidence; no runtime
changes. Independent reviewer: `journey_review`, a separate read-only agent.

## Verdict

Approved for diagnostic documentation after one wording correction. No blocking
correctness or privacy findings. Review is not scientific-quality certification.

The reviewer independently reconstructed the original reservation and five contrasts,
confirmed the context-selection contrast, thirteen settled ledger calls and estimated
usage totals, and resumed step 11. It verified six private artifact hashes, six
control receipt hashes, six completed measurements, archive restoration instructions
and Git exclusion. No live calls or run-state changes were made by the reviewer.

## Finding and resolution

- P3: The original draft said three resources were reread. The trace actually shows
  one repeated directory listing and two repeated file reads. Corrected to that
  precise description; the conditional causal interpretation remains unchanged.

## Validation

- `tests/test_agent_entry.py`, `tests/test_evaluation.py`, `tests/test_coding.py`,
  `tests/test_accounting.py`: **80 passed**, 25.48 seconds, branch source loaded via
  `PYTHONPATH=src` and the existing evaluation-enabled interpreter.
- Original context and budget replay probes fail their stated assertions as expected;
  contrast probes pass. This reproduces the observed limitations, not a shipped fix.
- Six real local Docker control measurements completed; repeat invocation reused
  the same six attempts and identical receipt hashes. No model calls in this control.
- Public-file heuristic scan and whitespace checks pass. Private configuration,
  raw model outputs, SQLite database and research inputs are excluded from Git.
- Full-suite and browser runs were not repeated for this documentation-only change;
  no production source, prompts, dependencies or scientific contracts changed.

See [the report](../evidence/representative-journey.md) for limitations and
[the evidence summary](../evidence/representative-journey.json) for measured values.
