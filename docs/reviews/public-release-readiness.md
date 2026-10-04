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
