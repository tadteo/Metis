# Review: bound evidence full text

Base `54df93a`; feature `37f8ae2`; review fixes `489314d`. Reviewer: independent
read-only agent `a9d5aa6` (not the implementer). Probes used synthetic data only.

## First pass (37f8ae2): approve with minor

Requirements verified: every AgentRunner request is bounded; gates (novelty
inspectability/citation, integrity, intake grounding) read stored evidence;
redaction precedes bounding and focus; projection is non-mutating and idempotent;
exact-copy references resolve; all IDs remain citable; all 48 agent versions and the
catalog (3.2.0 → 3.3.0) are bumped. Findings and resolution:

1. Minor: re-projection kept stale `windows`. Fixed in `489314d` (`windows: null`,
   `reprojected: true`, original size/hash kept).
2. Minor: abstracts-first allocation could leave priority evidence without full text.
   Fixed: priority evidence reserves up to half the budget before abstracts.
3. Minor: `review.py` projects without a focus, so review roles get leading excerpts
   and AgentRunner cannot re-window them. Accepted as an open risk.
4. Minor: `evidence_view.truncated` merged same-ID versions. Fixed: list entries carry
   `id` and `content_hash`.
5. Nit: any short context string became a priority ID. Fixed: only `evidence_ids`,
   `evidence`, `sources`, `source_ids` keys; `search_reports` excluded.
6. Nit: evidence nested in non-transport fields of evidence gets an empty passage.
   No current schema affected; accepted.
7. Nit: `agent_cache` events lack `evidence_view` (cache key includes the prompt);
   Laya typed advice uses its own transport without projection. Open risk.

## Re-review (489314d): approve

F1/F2/F4/F5 verified by probe (40 records: priority records receive 6,000 full-text
characters, abstracts shrink to 1,550, total exactly 80,000). New: the review-fix
commit's packaged matrix cites docs committed afterwards (resolved by the docs commit);
the half-budget reserve ceiling is now documented in `docs/ai-system.md`.
