# Model accounting

`Store` records monetary reservations and charges independently of agent roles.
Direct model calls use `reserve(..., kind="model")`, the default. An adapter that
runs several API calls uses `kind="aggregate"`, enforces its own call and monetary
caps before sending requests, and supplies durable `SubordinateCall` records when
settling the parent reservation. A parent reservation is not permission to exceed
the run's call limit.

```python
from autoresearch.accounting import SubordinateCall
from autoresearch.contracts import Usage

parent = store.reserve(run_id, "custom_adapter", maximum, request_hash, kind="aggregate")
# The adapter durably journals each attempted request before sending it.
children = [SubordinateCall.from_record("custom_adapter", row) for row in journal_rows]
store.settle(parent, aggregate_usage, subordinate_calls=children, stage=stage)
```

A child identity is `(run_id, namespace, child_id)`. Namespace identifies an
adapter's stable identity space; child ID identifies one attempted request, not a
response cache key. Resume reuses those identities. Different actual retry attempts
must receive different IDs. Child records retain provider/model/request identity,
usage, status and adapter details. `Store.subordinate_calls(run_id)` exposes these
facts and their parent relationship.

The parent charges cost and tokens once. Children count API attempts and explain
the parent's charge; their costs are never added again. Parent settlement, new child
facts and redacted `subordinate_model_call` events commit together. Replays with the
same facts are idempotent; changed facts or reassignment to another parent fail.
Aggregate totals must cover their children, including the estimated-usage flag.
Conservative reserved/failed SDK records remain charged when actual usage is unknown.
A reported monetary or call-count overrun is committed before `BudgetExceeded`
stops subsequent work. Independent late receipts may fill in previously missing
child facts if they remain consistent with the immutable parent settlement.

Usage retains `calls` as the reservation count and `model_calls_attempted` as the
number of direct reservations plus distinct child attempts. `aggregate_jobs` counts
aggregate reservations, and `subordinate_calls` counts child records. The historical
`writer_jobs` key remains a deprecated alias for `aggregate_jobs`; new consumers
should use the generic name. No budget calculation depends on role names or
writer-specific diagnostic events.

The explicit `aggregate_accounting_v1` migration imports older databases once in a
transaction. It classifies historical writer reservations and imports distinct
child identities from old diagnostic events while retaining all original calls and
events. Those events lacked parent IDs: imported children show
`parent_status="unassociated_legacy_event"` until a matching adapter recovery replay
establishes an association. The migration never guesses among several parent jobs.
Original duplicate diagnostic events remain visible, but do not duplicate attempted
call counts. Historical monetary totals and unresolved reservation holds remain
unchanged.

Historical diagnostics were redacted while SDK journals were private raw records.
A legacy record can be reconciled once when its identity and Usage remain identical
and the raw journal projects to exactly the imported redacted record. The ledger
marks it `legacy_reconciled`, retains the raw journal fact for exact future replay,
and leaves the original redacted events unchanged. This exception never permits
rewriting a native ledger entry or changing an incurred charge.

For paid decisions inside network-disabled research workloads, the optional
[experimental inference service](experimental-inference.md) reserves each explicit
API attempt against the same run ledger. Its controller receipts remain separate
from sandbox-writable copies; it requires operator startup and a recorded input
resource, without changing a saved run's behavior bundle.

## Request size and reservations

A direct model reservation is admitted before sending and is computed from the
request's byte length as a conservative token bound (`request_input_bound`), plus
the maximum output allowance, priced at the higher of normal and long-context rates.
Prompt size therefore drives every attempt's reservation, including failed and
rate-limited attempts. Literature records accumulate in `RunState.evidence` across
searches, so `evidence_context` bounds the model-facing passages per request (see
[AI system](ai-system.md#evidence-presentation-and-external-instructions)); stored
evidence is unchanged. In the 2026-10-07 replay a 1,413,835-byte novelty request
(USD 9.948 reserved) projects to 131,292 bytes (about USD 1.29 under the same rule);
see [the replay summary](evidence/bound-evidence-full-text-replay.json).
