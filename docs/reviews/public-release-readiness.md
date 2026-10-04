# Public release readiness review

Base: `70c81c1`. Branch: `codex/public-release-readiness`.
Independent reviewer: `release_review` agent, read-only review of the candidate
and [audit record](../evidence/public-release-audit.md).

## Scope and findings

The reviewer checked the README, documentation index, contribution and security
links, package version, third-party attribution, screenshot metadata and the
privacy claims in the audit. No unresolved release-documentation finding remains.

1. The README initially said 0.1.0 *is* an experimental preview before publication.
   Resolved by saying it is being prepared as one.
2. The audit called all `.png` paths PNG payloads; some contain JPEG data.
   Resolved by describing image blobs at `.png` paths and image metadata.
3. The address-scan result initially named only current captures after discussing
   historical images. Resolved by reporting the result across all 55 images.

The reviewer confirmed that the local links resolve and that ScholarPeer and
Ponytail attribution files are present. GitHub CI and final pushed-ref review
remain release gates; this independent document review does not replace them.

## CI repair review

After candidate push `4b70c66`, the branch's workflow failed before creating jobs.
Actionlint reproduced four unavailable `runner`-context expressions in job-level
`env`. The independent reviewer checked the focused `/tmp` replacement against
`4b70c66` and found no actionable issue. Both jobs use Ubuntu-hosted runners with
separate filesystems; the writer fixture and checkout paths remain identical.
Actionlint and whitespace validation pass. An actual GitHub workflow run remains
required before integration.

## CI validation result

The repaired workflow ran on private GitHub at `e2665ee`: both the pull-request
run `37217785408` and push run `37217785110` passed quality on Python 3.11 and
3.12 and passed the separate official-writer job. This is executable validation
of the candidate branch, not evidence of autonomous scientific quality. The
branch remains a draft PR; integration and public visibility still require the
user's authorization for the broad default-branch update.

The independent reviewer checked the final evidence against the private PR and
GitHub job results and found the CI, base/head and visibility claims accurate.
They identified a stale CI blocker in the draft PR description; it was replaced
with the two green run links and the remaining default-branch approval gate.

## Post-publication copy review

After the user approved publication, PR #1 merged at `0ce9b303` and main CI run
`37219943270` passed all three jobs. GitHub reported public visibility. The
independent `release_review` agent reviewed the focused README status change and
plan addition against `origin/main`; it found no actionable issue. The release
status now matches the public repository, the synthetic-demo and unmeasured
autonomy caveat stays verbatim, and the copy follows VIBE.md. Changed Markdown
links resolve, `git diff --check` and the public-file scanner pass. The prior
pre-publication review remains historical evidence.
