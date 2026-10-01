# Bounded provider fallback

Base d0e2fd8 (main advanced from 804c33b with a documentation-only merge before
the isolated branch was created). User requests automatic model switching on provider outages while
keeping research visible beneath an inline notice. Use the existing AgentRunner
boundary: recover only typed transport/429/5xx failures, after accounting for the
failed call. Select at most two alternate models from the saved enabled inventory
and project allowlist. Each attempted model gets its own reservation, event and
actual-model cache provenance. Stop on budget exhaustion, pause, invalid model
output, auth/config errors, or exhausted candidates. No new dependencies.

Preserve explicit heterogeneous panels, held-out evaluation, frontier escalation,
external commands, native writer calls and experimental comparison models. Automatic
fallback applies to ordinary orchestration roles using inventory routing. Explicit
legacy configurations remain explicit. Do not rewrite existing run fingerprints:
new behavior applies to newly created runs; current research remains saved.

Offline HTTP/runner checks must prove failure-to-success, actual costs/cache model,
allowlist and eligibility, all-fail bounds, nonrecoverable errors, pause and budget.
Use existing activity events for transparent switching and an inline status notice;
no modal/page replacement, implicit paid retry, or scientific-gate changes. Read
paper-spec/fidelity, architecture/ai-system/reproducibility, accounting/model-routing.
Independent review, full repository checks, provenance matrix, commit and merge.


## Validation history

Initial offline 429 case failed as expected. A subsequent fixture lacked required
limitations and was corrected to supply a valid scientific output. The invalid-output
plus failed-frontier test exposed a real fallback leak and passed after the protected
boundary fix; independent review exposed inherited held-out protection and that was
also corrected. Full pytest started before source edits finished hit two expected
behavior-drift guards; the stable-source full suite was restarted rather than
weakening those guards. Ordinary lint initially caught test import/lambda style and
was corrected. No live model calls or study-state changes were made.

Independent review approved; targeted fallback cases: 20 passed. Combined earlier
agent/provider/projection cases: 72 passed. Browser suites: 102 passed. Types pass
for 84 files; lint/format/specifications/public scan and scanner self-test pass.
Wheel build and installed-wheel check pass. Isolated offline demonstration completed;
it is synthetic, not evidence of scientific quality or live recovery.

Production-page synthetic previews at desktop and 390px, charcoal/cream, show the
inline switch notice with research navigation, costs and pause control still visible.
No popup, new page, hidden dashboard or added keyboard interaction is introduced.

Stable-source full suite: **1054 passed, 3 skipped** (344.10 seconds). The prior
in-progress run had 1048 passing, 3 skipped and 2 source-drift guard failures, as
explained above. Final validation preserves the guard rather than hiding failures.

## Final integration

Main independently gained stage reports and paused-timer fixes. The automatic merge
preserved them. The affected integrated suite initially had one fixture failure:
our synthetic RunState had empty timestamps, which the new timer projection parses.
Providing created_at/updated_at through existing now() fixes the fixture without a
runtime change; fallback_review approved and independently reran all 20 cases.
Final integrated checks: 133 Python tests, 103 browser tests, lint/format and types
(85 files) passed. All other active checkouts were clean at integration inventory.
The idle controller can load the update without advancing any saved research run.
