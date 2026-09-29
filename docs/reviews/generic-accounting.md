# Generic aggregate accounting review

Base: `fb5fc53`. Reviewer: catalog/platform agent, independent of this subsystem.

The review checked parent/child cost ownership, deduplicated attempt identities,
legacy migration/reopen behavior, uncertain parent relationships, conservative
unknown usage, transaction rollback and incurred-overrun preservation.

## Finding and resolution

The initial diff compared imported historical child events with private SDK journal
records exactly. Historical events had passed through privacy redaction, so a
private model name or home path caused valid recovery to conflict. Two regression
fixtures reproduced the failure before the fix.

The correction permits one legacy reconciliation only: child identity and Usage
must remain identical, the raw wrapper must agree with its details, and its saved
redacted projection must match the imported event record. Original events remain
unchanged. Reconciled/native records require exact equality on subsequent replay.

The reviewer rechecked the correction and reported no remaining blocking findings,
independently running all 10 accounting tests successfully. Implementation-side
validation passed 67 accounting/Store/security/writer/agent tests, Ruff and the
public scan; strict typing passed on accounting.py and store.py. Eleven engine tests
also passed before this isolated legacy-recovery correction. The full source type
check has only the inherited TUI override failure fixed separately by the coordinator.

An earlier malformed import placement caused three test collection failures;
correcting it preceded the passing focused suites. No model calls or research
capability measurements were made during this refactor.
