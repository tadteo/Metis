# Generic aggregate model accounting

Base: `fb5fc53`. Continuation of the AI-native architecture audit's finding that
Store understands PaperOrchestra-specific jobs and diagnostic event names.

## Boundary and design

Add explicit `model`/`aggregate` reservation kinds and a generic subordinate-call
ledger. Parent reservations settle monetary/token usage once; child identities
(run, adapter namespace, child ID) count attempts once. Commit child facts and parent
settlement in one transaction, retaining append-only conflict detection and charges
incurred beyond a reservation. A one-time migration classifies historical writer
reservations and imports historical child events without deleting either. Legacy
child events have no parent identifier: preserve that uncertainty and attach a
parent only when a matching recovery replay supplies it.

The writer remains responsible for its SDK journal, local call cap and conservative
unknown usage. Store has no ongoing writer-role or writer-event special cases. The
coordinator owns other writer imports/raw-material changes; edit accounting callsites
only. New adapter behavior is not scientific evidence.

## Acceptance

- Replayed parent/child settlement neither duplicates charges nor erases a measured
  or conservatively estimated charge; conflicting child identities fail closed.
- Generic reserve/usage count direct calls and subordinate calls using ledger data.
- Legacy migration preserves total costs, reservation holds, attempted-call counts,
  event history and unresolved parent relationships; reopening is idempotent.
- Focused budget, writer crash recovery and migration checks pass; lint/type checks
  pass except separately recorded inherited failures. Independent review before commit.

## Validation evidence

Implementation adds `accounting.py` contracts and explicit migration, typed
reservation kinds, atomic aggregate settlement, inspectable subordinate facts and
generic usage calculations. Writer SDK usage journaling remains unchanged.

- Focused accounting, Store, security, writer and agent suites: 65 passed.
- Ruff lint/format and public-content scan pass.
- Full strict typing reports only the inherited `tui.py:106` async override failure,
  already owned and repaired in the coordinator's integration branch.
- The initial writer import edit accidentally entered a TYPE_CHECKING block,
  causing lint parse errors and three pytest collection errors. Correcting the
  import scope resolved them; the successful focused suite followed that repair.
- Migration tests use an actual old SQLite layout, preserve duplicate original
  events and active holds, and recover both fully emitted and partially emitted
  old child events without duplicate billing. New tests inject a crash after the
  database transaction but before the writer's settlement marker.

Independent review completed by the catalog/platform agent; see docs/reviews/generic-accounting.md. No live API or scientific evaluation calls.

Independent catalog/platform agent review identified a legacy recovery conflict:
old diagnostic events were redacted while the SDK journal was raw. Two new
privacy-pattern/home-path fixtures failed before the fix. Recovery now permits a
one-time legacy reconciliation only when identity/Usage match and the raw journal's
redacted projection equals the imported record. Original events remain immutable;
subsequent native/reconciled record replays require exact equality. The resulting
accounting/Store/security/writer/agent suite passes 67 tests. All 11 engine tests also
passed before this isolated migration-recovery repair. Reviewer recheck found no remaining blocking findings and independently ran all 10 accounting tests successfully.
