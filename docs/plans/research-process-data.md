# Durable research process projection

Source: approved graph/Agent traces prototype and per-step time/cost request.
Implement a read-only, transactionally consistent projection of complete events,
reservation ledger, subordinate receipts and experiments. Preserve unknown timing,
unmatched attribution and failed/repeated attempts. Costs reconcile with Store usage;
child receipts explain parent charges without adding charges. Metadata allowlisting
and current privacy redaction prevent exposing raw prompts, outputs and SDK details.
Own process_view.py, focused tests, web endpoint/static allowlist. No engine changes.
Validate attribution ambiguity, parallel timestamps, late events beyond pagination,
failed/unmatched records, cost reconciliation, reservations and privacy. Coordinator
will obtain independent review and integration validation before merge.

Implemented complete single-transaction projection and authenticated process endpoint;
frontend process.js asset registered (provided by coordinator). Calls correlate only
through unambiguous request identities and durable call IDs. Preserved orphan starts,
interrupted executions, legacy experiment receipts, subordinate attempts and reentry.
Validation: 90 tests passed across process_view/accounting/web; focused mypy passed;
ruff format and lint passed. Independent review delegated to integration coordinator.

Integration follow-up: uniquely match state-only verification receipts to execution
start evidence without inventing end timestamps. Preserve every explicit transition,
including self-transitions, and reconcile terminal checkpoint/event clock ordering.
Linked agent metadata includes model/provider/panel index only. Added regression cases;
9 focused projection tests, mypy and ruff passed.
