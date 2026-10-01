# Metered experimental decisions

Base: d67c522. Implement an operator-started, run-scoped file service for model
inference inside network-disabled Docker experiments. The observed live intake
paused for lack of a shared-budget experimental inference interface; resuming
without an answer repeated intake. A read-only state check reproduced needs_access.

Use existing Store reservations/settlements, CompatibleProvider and secure filesystem
primitives. Keep runtime/specs/configuration hashes untouched so the existing run
can resume. Ship a standalone controller script and standard-library sandbox client;
record service source hashes, fixed provider aliases/rates, requests and receipts as
private run artifacts. Restrict service to saved primary/cheap providers, bound input
and output, one transport attempt per explicit request, and no credentials/network
inside workloads. Persist intent before dispatch and receipt before publishing;
never resend uncertain crash outcomes. Workspace copies are not trusted receipts.

Tests must cover no credentials in outputs, shared budget/call caps, failed/unknown
usage, deduplication across workspaces/restarts, interruption recovery, symlink and
malformed/oversized input rejection, pause behavior and concurrent service exclusion.
Run repository checks, independent review, commit and merge before live use. Supply
the interface as an explicitly recorded operator resource and answer via ordinary
intervention; resume same run without changing budget or deleting history.

This enables inference, not Laya installation, scientific success or writer setup.
All scientific work and paid smoke checks remain private runtime evidence.

## Completion evidence

Independent review approved (docs/reviews/metered-experiments.md). Focused tests:
18 passed, also independently repeated by the reviewer. Full suite: 1032 passed,
3 skipped. Browser suite: 98 passed. Ruff lint/format, mypy (84 source files),
48-agent/29-stage specification validation, public-file scan and its self-test,
wheel build and installed-wheel test (1 passed), and offline demonstration passed.
The demo is synthetic and supplies no research-performance evidence.

Preserved check history: the read-only original needs_access assertion failed as
expected; adding the wall-clock guard initially exposed seven fixture failures
because test runs omitted created_at. The fixtures now use a real UTC timestamp.
Review-discovered malformed-input, unsafe-response and stale-pause cases were
corrected and covered before the final passing checks.

All other active checkouts were clean at integration inventory; no concurrent work
was absorbed. No src/spec/config changes: the existing behavior identity can be
verified before supplying the recorded operator resource and normally resuming.
The live access check and subsequent scientific work are private Store artifacts;
their success must be inspected separately from this software validation.
