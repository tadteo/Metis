# Automatic project setup recovery

Base: `57e4d00`. The live-run review can ask the user to edit `project.include`
and fetch a Docker image even when Metis can perform those mechanical steps.

Implement bounded setup recovery from Check setup. When the selected folder has
eligible files but the configured include list matches none, choose an explicit
snapshot list from those files and recheck. Preserve protected evaluator files and
never include excluded, linked, oversized, or unreadable files. Readable binary
project assets remain eligible. When Docker is
running but the configured image is absent, build from simple pinned Python
requirements in a minimal context, or fetch the configured image when no unhandled
dependency manifest exists, then recheck. Do not
run project commands or claim that image dependencies or research behavior passed.
Keep an empty or wrong folder, unavailable Docker, and failed pulls actionable.

The browser applies returned configuration only when its edit revision still
matches the request. CLI and TUI readiness remain read-only; the mutation is a
separate authenticated web setup operation. Create and Start remain distinct.

Acceptance: focused source and Docker recovery regressions, stale-response browser
coverage, affected Python/Node/repository checks, both-theme visual inspection,
independent review, commits and merge. Record failed checks and limitations here.

## Implementation and validation record

The authenticated browser Check setup first performs the existing read-only preflight,
then calls a separate recovery operation for resolvable source/image blockers. Source
repair applies only to a complete inventory of at most 200 files and keeps literal
file selection, source exclusions, readability and the engine's text-context bound.
The returned draft is revalidated and the visible Docker field is synchronized with
the built image ID. Empty folders, excessive inventories and unsupported dependency
manifests retain actionable blocks. Simple pinned Python requirements build with a
context containing only the generated Dockerfile and requirements file; other selected
images can be fetched. Package installation, dependency behavior and actual benchmark
execution remain unverified.

Focused post-review checks: 41 setup/onboarding/authenticated HTTP tests passed;
62 browser logic tests passed. Ruff lint/format, mypy (72 source files), specification
validation, public-file scan and `git diff --check` passed. The full suite with a
null keyring passed: 907 tests, 3 skipped in 287.47 seconds. Its first run with the
host vault active had 902 passed, 3 skipped and one unrelated provider-test failure:
a saved `XAI_API_KEY` took precedence over the test's synthetic environment value.
The isolated failing test passed with a null keyring before the full rerun. The
initial offline wheel build with a fresh disposable uv cache lacked hatchling;
retry with the host's existing uv cache built the wheel. The offline synthetic demo
completed in a disposable private state directory; it is no research-quality claim.
The installed-wheel regression passed (1 test, 38.00 seconds). After the final
dependency-manifest detection edit, all 41 focused tests, Ruff lint/format and mypy
passed again.

Visual/interaction QA used a disposable loopback server and an empty synthetic
folder. At a narrow viewport, dark and light themes kept the readiness card, source
action and disabled Create control readable without horizontal overflow. At desktop
width the light review remained readable. Keyboard Check setup reached the review,
and Open project returned visible focus to the source field. A missing default image
was fetched during the dark walkthrough; no benchmark, model or research run started.
The review findings and fixes are recorded in `docs/reviews/automatic-project-setup.md`.
