# Independent review: automatic project setup recovery

Base: `57e4d00`. A separate read-only reviewer inspected the task diff and
`docs/plans/automatic-project-setup.md` for setup correctness, source privacy,
Docker behavior, stale browser state, and documented UX boundaries. The reviewer
did not run tests or certify scientific capability.

## Findings and resolution

- **Blocking:** A built image updated the draft JSON but left the visible Docker
  image field stale, so `readSetup()` would reject run creation. The field now
  receives the recovered image ID. A browser regression compares the visible
  field, form read and validated configuration.
- **Source inventory:** Excerpt truncation was conflated with file-list truncation,
  preventing automatic repair for ordinary projects with more than 35 readable
  documents. The inventory now reports its own completeness; a 40-module fixture
  verifies recovery.
- **Source selection:** Recovery now verifies readable regular files while keeping
  binary project assets, reports the 200-file/context bounds as a user action,
  and escapes glob metacharacters before storing literal selected paths. Tests
  cover unreadable assets, limits and a filename with brackets in an actual copy.
- **Image preparation:** Recognized dependency manifests outside the supported
  pinned Python requirements format block a bare default-image pull. Docker build
  and pull output is discarded instead of buffering an unbounded stream.

The reviewer made a final read-only pass, found no remaining blocking issue, and
reported `git diff --check` passing. Deterministic tests and visual inspection are
recorded in the task plan and are separate from this review.
