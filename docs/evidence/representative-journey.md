# Representative agent-led research journey

Date: 2026-09-30. Runtime: `67e70a9`. Diagnostic work only; no runtime or
scientific contract changes. See [task plan](../plans/representative-journey.md).

## Finding

The first hard blocker is **unbounded, poorly targeted literature metadata in the
limitations prompt**. Intake completed, but the next stage stopped before sending
a model request: the 654,640-byte prompt required a USD 8.334900 reservation against
USD 4.098618 remaining. The USD 5 guard worked. Raising the budget would conceal
avoidable input inflation and is not the recommended first intervention.

The limitations search uses the run title plus up to 1,000 characters of inquiry
text. Its twelve Crossref records include unrelated topics and whole journal issue
contents embedded in titles. Those titles total 301,623 characters; the largest is
119,969 characters (121,366 serialized). All twelve records appear in both
`state.evidence` and `retrieved`. This is a bounded single-task finding, not a
ranking across all research domains.

An offline replay reconstructs the recorded request and calls the real reservation
function. One-variable contrasts isolate the contributors:

| Diagnostic change to the saved request | Required reservation (USD) | Fits remaining cap? |
| --- | ---: | --- |
| Original | 8.334900 | No |
| Stage records reference existing evidence IDs | 4.531224 | No |
| Remove full text from both copies | 8.334900 | No; full text was already empty |
| Reserve only one transport attempt instead of three | 2.778300 | Yes, but changes retry protection |
| Bound title display to 500 characters in both copies | 1.136460 | Yes |

These are offline diagnostic contrasts, not patches, live treatments or endorsement
of an arbitrary 500-character production cutoff. Complete source records remain
unchanged. Relevant-literature selection still needs validation; shorter irrelevant
records would not make the research scientifically grounded.

The live journey lasted about 12.5 minutes from creation to stop, including the
intentional pause. It recorded 13 model reservations/completions and USD 0.901382;
USD 0.589636 of that total comes from two conservatively estimated usage records.
This is configured-rate accounting, not an invoice. There are no unresolved
reservations, research experiments, accepted baselines or paid compute charges.
Fourteen `agent_started` events include the limitations request rejected **before**
reservation/provider execution; event count is not remote API-call count.

## Secondary intake inefficiency

Intake lost useful immediate working context after literature discovery, repeated a directory listing, and reread
two source files. The trace reproduces an ordering problem:
`CodingSession._context()` selects recent steps using raw serialized sizes;
`AgentRunner._one()` subsequently applies `retrieval_model_view()`. Raw provider
responses and duplicate bibliographic records can therefore evict earlier
observations even though that transport data will not reach the model.

Following the second discovery, seven prior steps are omitted. The retained raw
step is 122,261 characters (122,263 in a JSON list), above the 100,000-character
recent-history allowance. Applying the existing projection before selection retains
all eight steps in 59,323 characters without changing the checkpoint. History
remains addressable; this is loss of immediate context, not deletion of provenance.
The model eventually requested history and completed intake. The mechanism is
proved offline; its contribution to live repetition remains an inference without a
paired live treatment. It was an inefficiency, not the final blocking condition.

## Experiment and boundaries

One normal agent-mode inquiry used the bundled public digits project, configured
xAI `grok-4.7`, and a USD 5 total model cap. No model substitutions, paid compute,
scientific-stage shortcuts or runtime patches were made. The fixed fixture has
1,797 observations: 1,347 training, 450 evaluation and a registered 404-row training
subset. Split seed is 20260929. The existing local Python Docker image was pinned
by digest. Scientific panel and seed defaults were retained.

The inquiry asks for an interpretable change to the standardized nearest-centroid
baseline, first reproducing it and preserving evaluation rules. It is a useful
small integration journey, not a frontier-research task. This fixture registers
measured baseline references rather than published SOTA. Whether the new agent-led
published-reference contract accepts that task remains untested downstream.

Preflight passed. It explicitly did not test provider access and warned that the
official writer checkout/environment was not provisioned. Live calls subsequently
confirmed model access. Setup command failures caused by this coding assistant's
filesystem/Docker sandbox were resolved by authorized execution permissions and
are not counted as product failures. A missing optional `CONTEXT.md` was also not
a product failure.

The live run was deliberately paused through the public interface for diagnosis,
then resumed through `Engine.resume` / `Engine.run(max_steps=1)` with the original
runtime and unchanged total budget. The first resumed request continued at step 11;
it did not recreate the session. All earlier observations remained available.
This is graceful checkpoint recovery, not a crash/uncertain-job recovery test.

## Hypotheses and negative results

- The initial context-selection hypothesis was supported by the real checkpoint
  replay. Model choice alone remains untested: no alternate model or prompt
  intervention was used. Recovery and eventual intake completion falsified the
  stronger claim that context omission permanently prevented intake.
- Total literature unavailability was falsified. Both early Semantic Scholar
  searches returned HTTP 429; both arXiv queries returned zero hits after combining
  every word of long natural-language queries with AND. Crossref supplied ten intake
  records, three with abstracts and none with full text at the first pause. This
  does not establish sufficient relevant coverage or scientific quality.
- At the hard stop, full-text volume was the initial competing explanation.
  Removing full text left the reservation unchanged because those fields were
  already empty. The first contrast asserting a decrease failed and is retained as
  a negative diagnostic result. Large title fields, duplication and conservative
  retry reservation were the confirmed contributors.
- Deduplication alone was insufficient for this cap; title-size bounding was
  sufficient to make the saved request reservable. Neither has been tested for
  live scientific quality. Disabling retry coverage was diagnostic only; the live
  budget and retry policy were never weakened.

## Local execution control

A separate copy of the public fixture executed the unchanged baseline through the
normal Docker executor. All six attempts completed: three registered seeds each
for subset and full training. Subset accuracy was 0.8755555555555555 for each seed;
full accuracy was 0.8777777777777778. Recorded execution durations totalled about
6.49 seconds. The deterministic repetitions measure reproducibility, not statistical
significance. A second `baseline_suite` invocation preserved all six receipt hashes
and the six-attempt count. No control result was imported into the agent-led run.

This establishes local fixture execution and completed-receipt reuse. It does not
establish autonomous coding, agent-created evaluator integrity, baseline acceptance,
scientific novelty, manuscript quality or capability parity. Those stages were not
reached in this diagnostic; intake alone completed.

## Reproduction and retained evidence

The private evidence package retains the original configuration, prepared source,
CLI outputs, state database and run tree, raw retrievals, all request/response events,
checkpoints, control receipts and diagnostic scripts. Do not commit that package.
The adjacent machine-readable summary contains sanitized configuration metadata,
reviewed counts and hashes.

Using the original runtime and interpreter with the evaluation dependencies:

```bash
# JOURNEY_ROOT identifies the unpacked private evidence package.
PYTHONPATH=src python "$JOURNEY_ROOT/replay.py"    # expected assertion failure
PYTHONPATH=src python "$JOURNEY_ROOT/contrast.py"  # expected success
PYTHONPATH=src python "$JOURNEY_ROOT/budget-replay.py"   # expected assertion failure
PYTHONPATH=src python "$JOURNEY_ROOT/budget-contrast.py" # expected success
PYTHONPATH=src python "$JOURNEY_ROOT/control.py"         # reuses completed receipts
```

The private scripts bind to the recorded original location; restore that location
before replay, as documented in the private archive index. These diagnostics make
no model calls. Never resume the live run just to reproduce context selection.
The replay intentionally accesses a private method; it is a diagnostic harness,
not a proposed stable public API or an ordinary failing CI test.

## Next investment

Prioritize a focused retrieval-to-prompt change before any coding-agent migration:

1. Build focused search queries from the grounded research brief rather than the
   whole inquiry. Detect or refine obviously off-topic results before dispatch.
2. Give each stage a bounded model-facing evidence view: short metadata, IDs and
   accessible source passages, without duplicating entire records. Preserve raw
   retrievals and make omitted content addressable. Exercise pathological title
   records and ensure arbitrary scientific fields survive projection.
3. Apply that projection before intake history selection. Cover nested history and
   oversized single observations with regression tests.
4. Repeat this task as a separately registered live treatment. Acceptance requires
   relevant grounded sources and progress beyond limitations within the same cap,
   followed by an actual accepted baseline. A smaller prompt alone is insufficient.

A 2–4 hour engineering timebox for the bounded projection, adverse tests and one
repeat is a planning estimate, not a claim of measured savings. Query relevance may
need further iteration. This should have greater immediate value than replacing
`AgentRunner` with another agent backend: the observed failure occurs in shared
retrieval/context preparation before the next model call or coding execution.

Writer provisioning remains necessary for a complete manuscript journey, and the
fixture's measured-reference versus published-reference distinction needs explicit
handling. Neither downstream concern was tested here. No runtime fix is included
in this diagnostic delivery, and the live budget was not increased.

## Follow-up implementation (2026-10-01)

The [bounded evidence context task](../plans/bounded-evidence-context.md) implements
presentation bounds, exact-copy request references and projection before history
selection, with privacy-redacted paging for oversized observations. The
[offline replay summary](bounded-context-replay.json) records a 46,871-byte request
and USD 1.048452 reservation under the updated prompt, retaining all eight intake
steps without changing the original checkpoint. No new live model run accompanies
this treatment; the relevance problem and accepted-baseline outcome remain open.

Partial results are visible through the app's process graph, Agent traces and
Artifacts views. This diagnostic has a sourced intake brief and literature evidence;
the six measured control executions documented here belong to the separate baseline probe,
not an accepted experiment in the stopped research run. Durable run state/events/
usage live in private SQLite; artifacts, coding checkpoints and command receipts
live in the Store's run directories. The private archive preserves them together.
