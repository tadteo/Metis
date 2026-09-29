# Writer failure recovery

Initial base: `0bdbd07`; reviewed integration foundation: `357d4a3`. Branch: `codex/writer-recovery`. Status: independently reviewed and validated on the committed foundation.

## Provenance and scope

The worker integration foundation is copied from the frozen `codex/official-writer` worktree.
It was developed after the honest import by another existing chat; these changes are not
attributed to a fictional earlier implementation history. This task owns only the worker,
its recovery regression tests and this plan. Parent accounting and reference provisioning
remain separate tasks.

## Plan

1. Capture swallowed budget errors, premature stage checkpoints and incorrectly resolved
   request failures as deterministic failing tests.
2. Persist all blocked/failed requests, carry stage context through nested executor work,
   and reject a stage before checkpointing when its transport work remains unresolved.
3. Reuse successful responses on resume; require a later success in the same stage to
   resolve a failed request. Preserve failed rows and reject ambiguous legacy evidence.
4. Exercise actual pinned upstream classes with injected transport responses when feasible;
   never make paid API calls, and distinguish simulated compilation from real LaTeX checks.
5. Run focused tests, lint and type checks. Request independent review before committing;
   record findings, evidence and their resolutions.

## Review findings driving this task

- Budget/adapter errors thrown before request journaling are swallowed by upstream agents.
- Validation after stage checkpoint creation makes failed jobs permanently unresumable.
- An older successful request must not erase a later exhausted identical request.

Initial real-upstream reproduction: `ContentRefinementAgent._get_formatting_review` on a
synthetic one-page PDF with a USD 0.10 allowance returned an error after retries, while the
usage journal stayed empty. No network request was sent.

## Implemented and verified

- Every top-level transport invocation now receives a durable request receipt before adapter
  validation or budget reservation. Receipts include stage, identity and terminal outcome;
  nested billing calls retain their observation ID without duplicating adapter observations.
- Stage identity propagates through upstream nested executor pools. A failed request is
  resolved only by a later successful identical request in the same stage. Stage checkpoints
  are written after validation; poisoned checkpoints and downstream checkpoints are revoked
  with an explicit invalidation record. Unscoped legacy failures require reconciliation.
- The worker takes an exclusive nonblocking POSIX file lock before reading journals and
  records PID, host, running/completed/failed status and start/end times.
- Three initial tests failed before the fix because swallowed failures incorrectly wrote
  checkpoints. Nine recovery tests now pass, including an actual pinned upstream
  `ContentRefinementAgent` smoke that uses real PDF rendering and parsing with injected SDK
  responses. The test proves that five refused calls remain recorded, no request is sent
  under the exhausted allowance, and the same stage completes after budget recovery.

Validation commands (from this worktree):

```bash
PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_writer_recovery.py
AUTORESEARCH_UPSTREAM_FIXTURE=/path/to/pinned/checkout PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_writer_recovery.py
ruff check src/autoresearch/paper_orchestra_worker.py tests/test_writer_recovery.py
mypy --follow-imports=silent src/autoresearch/paper_orchestra_worker.py
```

The ordinary development environment runs eight tests and skips the optional upstream smoke.
The provisioned upstream SDK environment runs all nine in approximately three seconds.
Focused lint/type checks pass. The older `tests/test_writing.py` on this branch still invokes
the removed local writer signature and fails independently; the official-writer integration
branch owns its replacement. No paid API calls or real LaTeX compilation were performed.

The coordinator independently ran all nine recovery tests, including the actual upstream
smoke (nine passed in 2.30 seconds), and approved the focused delta. The complete original
work was preserved in a filesystem snapshot and a Git stash before fast-forwarding this
branch to `357d4a3`. The recovery delta was reapplied with a three-way merge; the only overlap
was formatting around the intentionally replaced global failure check. Newer subordinate
call limits, conservative price markers and protected plotting workload paths were retained.

Integration validation on `357d4a3` plus this delta: writer recovery, writer contracts,
architecture gates and store tests passed together (53 passed, one optional skip). The
separate actual-upstream recovery run passed all nine tests in 2.45 seconds. Ruff lint,
format checks, strict worker typing, public-file scan and Git whitespace checks passed.
The formerly stale writer-interface test is resolved by the foundation commit.
