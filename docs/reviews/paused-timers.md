# Independent review: research interface timers

Base: 804c33b. Reviewer: separate review_timers agent, read-only diff review.
Checked correctness, pause/resume, cooperative checkpoints, repeated holds,
unknown timing and preservation of measured receipts and scientific behavior.

Finding P2: cancellation sets paused state but experiment_cancelled has no status
payload. Without recognizing its kind, resume added the cancelled interval back.
Resolved by adding the durable event marker and exact-payload regression.
Reviewer verified resolution: 15 focused tests passed (endpoint excluded in its
sandbox). Parent ran the authenticated endpoint with permissions successfully.
No remaining actionable findings within recorded-hold scope. Historical unrecorded
idle intervals remain unavailable; the display uses checkpoint fallback while idle.

Validation: 16 projection cases passed; related API suite 89 passed before the
additional cancellation case; 101 browser checks passed; lint, format, focused types,
public scanner and diff checks passed. No scientific performance claim.
