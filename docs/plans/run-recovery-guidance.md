# Explain blocked research runs

Base: 236da46. User cannot understand the saved HTTP 429 or whether to change Gemini
billing. Browser-only repair: replace the bare error with a reason, last recorded
model when identifiable, provider guidance, explicit resume semantics and expandable
original error. Correct the contradictory stopped-run overview copy. Keep existing
resume controls, accounting, retries, provider configuration and pinned runtime
unchanged; make no paid diagnostic calls or automatic restart.

Reproduce via real renderDetail with a blocked-run fixture. Cover 429 uncertainty,
503, authentication and unknown errors, escaping and active/stale-error behavior.
Inspect desktop/narrow layouts in light/dark with keyboard access to details and
links. Use synthetic visual evidence; review independently, validate and merge.

The saved provider error intentionally omits its response body, so this change cannot
recover whether a historical 429 was rate, quota or billing related. Link to official
Google limits guidance without asserting that payment fixes the problem.

## Validation and integration

The initial renderDetail regression failed: it found only the HTTP 429 string,
not rate-limit/quota guidance. After the fix all 100 browser tests pass. Relevant
web and behavior suites: 90 passed. Ruff lint/format and diff checks passed.
Independent review approved after reusing raw-details for long-error wrapping.
Synthetic production-renderer previews inspected at desktop and 390px in both
cream and charcoal; keyboard Enter opens details with a visible focus indicator.
The historical response body is unavailable: precise provider quota diagnosis
remains an account-side check. No paid calls or run restart were performed.
