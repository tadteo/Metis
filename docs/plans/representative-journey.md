# Representative research journey diagnosis

Base: `67e70a9`. Status: validated and independently reviewed; ready for integration.

## Request and experiment

Exercise the newly integrated agent-led path and identify the biggest observed obstacle
to useful research. Use one bounded public task, private run storage and normal public
entry/execution interfaces. Register inputs, success criteria, commands, failures,
interventions and limits before making claims. Do not infer capability from unit tests.

Initial scope: question plus a small public existing project/task, through intake,
baseline preparation, real measurement and checkpoint recovery where available. Inspect
local model/compute readiness first. The user authorized configured models up to USD 5, with no paid compute.
Use the existing local Docker image, public inputs and a private run store.
Retain configured scientific counts and pricing; report ledger estimates separately
from provider invoices. No speculative runtime upgrades or model substitutions.

Success means a reproducible evidence report: stages actually reached, exact blocker,
competing explanations tested, preserved failed attempts and a prioritized next action.
If a bounded defect warrants repair, reproduce before changing it and follow the
repo's tests/review/commit/merge workflow. Broader scientific changes or a backend
migration are outside this diagnostic task. Keep original source and existing runs
unchanged; inventory other worktrees before integration.

## Registered execution

- Runtime base: `67e70a9`; branch: `codex/representative-journey`.
- Configured provider/model: xAI / `grok-4.7`; vault credential available.
- Public digits fixture: 1,797 rows, fixed split seed 20260929; 1,347 training,
  450 evaluation, 404 registered subset training rows.
- Entry: normal CLI `new` then `run --steps 1`, explicitly agent mode.
- Limits: USD 5, 60 model calls, 3,600 seconds; stop at first unresolved blocker,
  first accepted research baseline, or budget exhaustion.
- Independent control: execute the unchanged public baseline in local Docker,
  then repeat to verify receipt reuse. Never import control results into the live run.
- Preflight accepts entry, warns that model access is untested and the official
  writer environment is not provisioned.

## Outcome

Intake completed after a deliberate pause/resume diagnostic. The next stage stopped
before provider execution: a 654,640-byte limitations prompt needed a USD 8.334900
reservation with USD 4.098618 remaining. Final ledger charge was USD 0.901382,
including USD 0.589636 conservatively estimated usage; no outstanding reservation.
No baseline coding or research experiment was reached. Six separate compute-control
measurements passed and reused identical receipts.

The main finding is oversized, off-topic literature metadata duplicated in the
model context. A second finding is intake history selection before transport
projection. The full report preserves negative probes and distinguishes deterministic
mechanisms from untested live improvements. No runtime repair, backend change,
budget increase or scientific claim is included.

Deliverables: [report](../evidence/representative-journey.md),
[machine-readable evidence](../evidence/representative-journey.json), private archived
raw evidence, and independent review. No fidelity-matrix component status changes
are justified by this single diagnostic run.

## Integration inventory

Main was clean at 67e70a9. Other uncommitted work in onboarding-review,
temple-refinement-review, temple-review and temple-stage-prototype was inventoried
and left untouched. Only this task's three documentation/evidence files and the
review record are in scope.

## Validation and review

The relevant intake, coding, evaluation and accounting suites pass: 80 tests in
25.48 seconds. Both original offline probes reproduce their expected assertion
failures; both contrasts pass. Public-file and whitespace checks pass. Independent
review approved the evidence with one P3 wording correction, now resolved; see
[review record](../reviews/representative-journey.md). No full-suite or browser rerun
was needed for this documentation-only delivery.
