# Bounded evidence context review

Base: `e6bee9f`. Independent reviewer: `journey_review`. Date: 2026-10-01.

Scope: schema-aware evidence presentation, exact-copy JSON references, coding/intake
history selection and recoverable paging, shared external prompt guidance, and
preservation of scientific evidence and accounting. This is an engineering treatment
of the representative journey's request-size failure, not a scientific fidelity claim.

## Findings and resolutions

- P1: Serializing/paging raw history before redaction could split known secrets or
  bypass structured secret-key handling. Redact the complete structured observation
  first, then page its JSON. Expose separate original and redacted-view hashes.
  Regression reconstructs seven-character pages and confirms no credential leakage
  and unchanged original steps.
- P2: References generated before redaction could point into a removed secret field
  or have their JSON Pointer changed by custom patterns. Redact before projection
  and exact-copy reference construction; verify every surviving reference resolves.
- Follow-up privacy boundary: Bounding titles/venues before redaction could retain
  partial secrets. Redact complete values before any projection in AgentRunner,
  recent history and published review prompt/context preparation. Boundary fixtures
  failed before correction and pass afterward, retaining the original raw evidence.
- Test-scoping correction: the review fixture also intercepted final panel input
  before its AgentRunner redaction. Restrict the assertion to the review subcalls;
  separate actual-runner tests cover the final provider request boundary.

The reviewer inspected the final runtime and independently passed the corrected
review-boundary regression (one test, 0.70 seconds). Approval: no remaining
actionable findings. Coordinator's affected suite passes 61 tests. Full release
validation and integration are recorded in the task plan.

Offline private-trace replay reproduces a 654,640 to 46,871 byte prompt reduction,
USD 8.334900 to USD 1.048452 reservation reduction under the current prompt, and
retention of all eight intake steps in 59,323 characters. Original checkpoint hash
is unchanged. Only the aggregate replay summary is public. It does not establish
source relevance, scientific progress, or quality parity with ScientistTwo.
