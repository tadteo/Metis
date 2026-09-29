# Preserve partial ScholarPeer evidence

Base: reviewed writer integration and recovery (`39a9385`).
Status: implementation tested and independently reviewed; ready for focused commit.

## Ownership and provenance

This focused task owns ScholarPeer review persistence, its AgentRunner checkpoint callback,
a regression suite and this plan. It reuses the completed writer-recovery checkout on a new
isolated branch; the prior commit remains intact. Pending `review.py` improvements from the
original checkout include semantic repairs, model-view deduplication and a complete expansion
ledger. They predate this task and will be integrated explicitly, without importing unrelated
coding or integrity changes from `agents.py`.

## Plan

1. Reproduce a late novelty/technical QA failure through the real AgentRunner and Store;
   assert raw search reports, excluded references and rejected semantic outputs survive.
2. Add durable immutable checkpoints before and after model/retrieval boundaries, plus a
   terminal failure snapshot. Preserve all attempts and structured validation errors.
3. Keep published prompts, all literature expansion results, repair/escalation behavior and
   accepted scientific context intact. Snapshot concurrent historian/scout outputs safely.
4. Test late failure, partial retrieval failure, repeated attempts and successful completion;
   run relevant existing review/architecture/provider suites and lint/type checks.
5. Obtain independent root review, record evidence, then create a focused Conventional Commit.

Acceptance: a failed review has inspectable persisted evidence even if `review_context` never
returns and no engine state save follows. A retry never overwrites earlier attempt artifacts.

## Implementation and evidence

`review_context` now emits immutable snapshots at retrieval/model boundaries and on failure.
AgentRunner immediately writes each snapshot to the run artifact store with a unique review
attempt identifier, so retries at the same run version preserve all prior artifact bytes.
Concurrent historian/scout outputs are synchronized before snapshotting. Semantic rejection
records survive repair exhaustion, and semantic escalation reaches the frontier model route.

The initial regression ran against the inherited behavior and failed because zero checkpoint
artifacts existed after late QA failure. After implementation, six new regressions cover late
semantic repair exhaustion, partial provider failure, parallel role failure, immutable retry
history, frontier escalation, and preservation of scientific fields whose names match
transport metadata. The combined review, architecture, agent and literature
suite passed 55 tests. Focused Ruff, mypy, secret scanning and `git diff --check` passed.

Inherited `review.py` improvements were copied from a frozen source with SHA-256
`f79619f7e64ea610d1fd2cc787b0694ad5ac8c014dc25bac9ceea6e177499f32` before adding
checkpoint persistence. They are not fabricated historical work. The tests use deterministic
model/retrieval fixtures and the real AgentRunner/Store; they establish evidence retention and
control flow, not scientific review quality with live providers.

## Independent review follow-up

Root identified an inherited blocker: the recursive model-view filter removed any dictionary
field called `record`, `raw_source` or `raw_response`, including scientific experiment records.
A regression reproduced the data loss. The filter now recognizes the complete Evidence schema
and the Literature search-report schema, removing duplicates only at their specific transport
boundaries. Arbitrary scientific keys, nested measurements and excerpts remain intact. The new
regression also confirms immutable checkpoints retain original retrieval transport bytes.
