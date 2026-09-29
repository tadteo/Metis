# Official PaperOrchestra integration review

The integrated source was developed concurrently by the existing writer chat after the honest
prototype import. This branch preserves that work as an integration delta; it does not invent
its development history. The coordinator independently inspected the pinned upstream topology,
transport bridge, stage orchestration, plotting sidecar and immutable artifacts. Reviewer
workflow_review separately checked recovery and plotted-output isolation.

Reviewed upstream: google-research/paper-orchestra at
ca1b3fa01c2970fc7cda32d16245db38d57b3f56. Actual pinned OutlineAgent smoke uses injected responses;
all five official agent classes import. This demonstrates executable integration, not scientific
performance. The hash-locked runtime is used by the opt-in upstream suite.

The review found defects requiring focused follow-up commits before main integration:

- Swallowed transport errors can certify a stage; fix stage-scoped receipts and recovery.
- A dead Docker client or process leader can leave spending descendants; verify worker exit.
- Reservation recovery must preserve durable intent and only reserve the remaining cap.
- Installed plotting references must match the actual checksum-pinned archive, including reuse.

Regression suites and independent review for these fixes are recorded with their commits. The
foundation is committed on the isolated branch; it is not accepted as complete on its own.

Latest sidecar review: workflow_review independently passed four tests covering output symlink
protection, atomic temp creation, timeout cleanup and generated-code completion forgery. The
coordinator confirmed writer outputs use official agents; no simplified writer fallback exists.
