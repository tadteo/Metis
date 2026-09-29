# Project-first onboarding

Base: 38910cb. Request: simplify live project setup and the transition to research,
using an existing remote GPU project as the motivating case. Existing setup exposes
internal JSON before explaining the work needed and can overstate scheduler readiness.

Implement a project-first path: bounded read-only source discovery, evidence-backed
command candidates, plain-language decisions, reusable private settings, an actionable
readiness summary and a review of the saved run before explicit execution. Preserve
manual advanced configuration and existing scientific gates. Never execute discovered
commands, infer scientific reference values, or automatically accept an evaluator.
Detect scheduler launcher requirements which the generic backend cannot satisfy.
No private project paths, source, credentials or cluster data enter public fixtures.

Use existing source admission, settings validation, preflight and run creation seams.
Repository content is data, never executable setup instructions. Candidate application
must be explicit, preserve unrelated configuration and invalidate previous validation.
Live creation requires server-side checks. Setup reports configuration checks separately
from actual measurements and external service verification. No paid calls or scheduler
jobs are authorized by this implementation task.

Validation: synthetic discovery/unsafe-file/ambiguous-launcher fixtures; authenticated
HTTP boundaries; browser state, stale-response, candidate selection and creation tests;
visual QA; repository formatting/types/specifications/Python/Node/scanner/demo/wheel
checks. Independent agent review in a separate checkout, resolve findings, commit,
update fidelity with the actual feature SHA and merge. Preserve failed checks here.

The user has been asked whether onboarding should additionally use an AI assistant to
prepare missing adapters; scope will incorporate their answer before dependent work.

User selected inspection plus AI assistance, especially for existing projects. Implemented
bounded local discovery, an explicit paid-request preview, separately budgeted private
proposal receipts with no automatic retry, evidence-cited settings and inert adapter
drafts, explicit selected-suggestion application, and plain command inputs. The new
project path opens manual experiment details. Existing research execution contracts
remain intact; this task does not implement target-specific GPU scheduling.

Initial checks: one old browser test expected JSON-only commands; updated for the new
plain-command behavior and added quoting/operator regressions. Six preparation tests
failed on calling catalog.digest as a function; fixed to use its property. Mypy found
a reused HTTP result variable with incompatible types; renamed. Ruff caught an unsafe
absolute temporary fixture path; changed it to a synthetic non-temporary path. After
fixes, 12 onboarding tests and 34 browser tests pass; all 68 source files pass mypy.

Independent review found one P1: current project/execution settings were included in
the AI request but absent from the preview. Fixed by exposing the exact outbound
system/prompt and destination and redacting structured input before JSON serialization.
Added a sentinel/redaction regression. Reviewer approved after 111 Python and 34 Node
tests. Review also clarified that launcher detection covers recognized launchers, not
arbitrary submission logic. New default navigation is Project → Model → Review;
advanced settings remain reachable.

Validation on frozen task source: 859 passed, 3 skipped in 260.65 seconds; installed
wheel test passed separately. All 68 source files pass mypy; Ruff lint/format, specs,
public scanner/self-test and 35 browser tests pass. Browser walkthrough used a local
synthetic provider and public fixture only: request preview, proposal, reload/recover,
selected application and review; both new/existing entry paths, themes and responsive
layouts checked. No paid calls or cluster jobs were run. Private fixture/screenshot
state remains outside the public repository.

During validation main advanced through the separately reviewed inquiry interface and
VIBE.md aesthetic guide. Read VIBE.md and preserve those changes when integrating;
rerun affected browser/web/interface checks after any conflict resolution.
