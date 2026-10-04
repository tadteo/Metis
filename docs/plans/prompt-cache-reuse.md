# Prompt cache reuse

Base: 88b2c6f. User reports inefficient API usage and inconsistent prompt caching.
Reuse the clean completed stage-reports checkout on codex/prompt-cache-reuse.

Diagnose with saved-request prefix comparison and synthetic HTTP requests. No paid
calls, private-record mutation, budget increase, or automatic research continuation.
Check three hypotheses: missing xAI conversation affinity; changing checkpoint fields
before reusable evidence; discarded cached-token receipts. Preserve full scientific
context, JSON Pointer paths, independent critics, local exact-response cache identity,
conservative reservations, and all prior failed attempts.

Implement stable reference-first messages with ordered eight-record evidence chunks,
a trailing dynamic context message, xAI-only documented chat conversation
routing, and nullable cached-input token telemetry through provider and Store usage.
Do not invent a cache discount or rewrite historical charges; provider prices and
unknown usage remain explicit. No new response/session storage, context truncation,
provider switch, or retained reasoning replay. Provider caching is opportunistic.

Acceptance: real AgentRunner requests retain all state and held-out isolation while
feedback/counters change only the trailing context; appended evidence retains complete
prior chunks, edits invalidate affected prefixes, and split messages reconstruct the
canonical context exactly; reservation and unknown-usage bounds include framing; HTTP routing stays stable across
requests in the same run/model/system, differs across runs/roles, and is absent for
other compatible endpoints; stream and JSON cached-token receipts survive retries
and ledger settlement, with malformed/absent counts remaining unknown.
Measure before/after shared prefix offline; that is eligibility evidence, not a
measured server cache-hit rate or scientific-quality result. Focused and full tests,
repository checks, independent review, commit, fidelity evidence and merge required.

Sources checked 2026-10-02:
- https://docs.x.ai/developers/advanced-api-usage/prompt-caching/maximizing-cache-hits
- https://docs.x.ai/developers/advanced-api-usage/prompt-caching/best-practices
- https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing

Review found that one reordered JSON message was insufficient for xAI's documented
whole-message matching. Splitting only reference/current also failed when new evidence
was appended, so ordered evidence chunks preserve the already-read message prefix.
