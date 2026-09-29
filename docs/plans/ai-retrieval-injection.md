# Propagate the pinned retrieval adapter into review

Base: `f63e123`; isolated branch: `codex/ai-retrieval-injection`.

Final Spec review found that Engine's injected literature adapter was pinned and
used for novelty/reference audits, but the default AgentRunner silently constructed
a new Literature during ScholarPeer review. Pass the same explicit dependency to
that runner. Preserve native PaperOrchestra retrieval as its separate pinned
upstream boundary; custom runner factories remain responsible for their dependencies.

A shared adapter also exposes two lifecycle assumptions: review temporarily changes
its publication cutoff and currently includes all cumulative search reports. Restore
the cutoff even after failure and retain only this review's reports in its context,
without deleting any adapter history. This preserves resume identity and honest
review-specific coverage.

Acceptance: an offline live-protocol fixture records actual injected retrieval calls
and evidence in real model requests; interrupted review retains evidence; review
completion/failure leaves stable adapter identity; a recreated same-identity adapter
can resume and changed identity blocks before model calls. Relevant scientific,
provenance and review tests, lint/type checks and independent review precede commit.

The two live-protocol fixtures first failed at the actual-query assertion: the
injected adapter was never called. After wiring and lifecycle repair, both passed.
Added direct-run counterexamples for omitted and changed pinned adapters; review is
refused before any model/retrieval request. Focused retrieval, behavior, agent,
ScholarPeer persistence and literature suites passed **81 tests** (11.09s). No
external model or retrieval request was made. Independent source review approved all four adverse/live-protocol fixtures; see the
review record. Scoped Ruff, strict mypy on three modules and whitespace checks passed.
