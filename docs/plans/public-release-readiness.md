# Public GitHub release readiness

Base: `70c81c1`. Branch: `codex/public-release-readiness` in an isolated managed worktree.

## Requirement and boundary

Prepare the existing private Metis repository for a public GitHub preview. Preserve the
scientific limitations and every historical attempt. Do not change repository visibility,
publish a release, or claim autonomous research quality as part of preparation.

## Acceptance

- Audit tracked files, reachable Git history, and binary evidence for private content and
  third-party attribution. Record findings and disposition without reproducing secrets.
- Verify the README, contribution guide, security policy, license, and user documentation
  remain accurate and navigable for a new public reader. Fix concrete errors only.
- Run the release checks from CI, including the wheel, scanner, synthetic demo, and
  official writer integration where the environment permits. Distinguish blocked checks
  from passing checks; obtain GitHub CI on the candidate branch.
- Obtain independent review, resolve findings, commit the focused changes, and merge only
  after the applicable validation passes. Keep the final visibility change for explicit
  user approval once the candidate and evidence are reviewable.

## Local validation and review

The candidate changed documentation and evidence only. The independent reviewer found
three wording issues; all were corrected in [the review record](../reviews/public-release-readiness.md).

At the reviewed candidate: 1,093 Python tests passed and 3 skipped in 404.32 seconds;
106 browser tests passed; formatting, Ruff, mypy (86 source files), 48-agent/29-stage
spec validation, secret scan and scanner self-test passed. The synthetic offline demo
completed with `previous_best_retained_meta_refinement_not_superior` and no error.
The final wheel built and its installed-package check passed (1 test). Local Markdown
links resolved across 201 pages, including the audit and review records. GitHub CI
and exact pushed-ref verification remain pending.

## GitHub CI diagnosis and repair

After pushing candidate commit `4b70c66`, private GitHub Actions run `37217023746`
failed at creation with zero jobs and no logs, matching three earlier runs. The
pinned actionlint v1.7.12 binary, downloaded from its official release and SHA-256
verified, reproduced four expression errors: `${{ runner.temp }}` is unavailable
in job-level `env` at workflow lines 23 and 63–65. Both jobs explicitly use
`ubuntu-latest`, so replace those values with job-private `/tmp` paths. Re-run
actionlint, local release checks affected by CI config, and a new private GitHub
workflow run. Request an independent review of the workflow correction before
merging. Preserve the failed runs as evidence; do not present them as test failures.

The four-line workflow correction passes actionlint v1.7.12 and `git diff --check`.
The independent CI reviewer found no actionable issue; see the review record.
The prior zero-job runs remain failed and retained. Push this focused repair to
trigger the actual Ubuntu jobs before considering integration.
