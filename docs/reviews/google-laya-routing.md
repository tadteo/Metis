# Google and Laya routing review

Base: `cbdd55c`. Independent reviewer: `/root/review_google_laya`.

Reviewed profile routing, custom overrides, credentials, CLI/web settings,
Laya fallback, scientific gates, offline-test isolation and interface behavior.
Initial review ran 44 focused Python tests and 65 browser tests. An initial
review command named a nonexistent test_routing.py; corrected to available suites.

## Finding and resolution

P2: a credential save/removal response could be displayed under a changed
provider target, and save completion could erase newly entered input.
Resolved by capturing the destination, locking credential controls during
mutation, invalidating pending profile revisions, suppressing stale successes,
and preserving subsequent input. Two deferred-response regressions cover it.

Re-review: no remaining actionable findings; all 67 browser tests passed.
Reviewer accepted CSS scroll padding; implementing agent performed the actual
narrow/desktop light/dark visual and keyboard checks. Evidence is linked in
[the task plan](../plans/google-laya-routing.md). Approval is engineering review,
not measured research quality. Full suite: 913 passed, 3 skipped. Package check,
types, formatting, lint, specs, public scan and synthetic demo passed.

The unexpected provider request from the pre-existing credential test and its
isolation fix are retained in the task plan; billing is unknown. No live Google
or Laya capability or savings claim is made.
