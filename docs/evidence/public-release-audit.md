# Public release audit

Scope: the Git history reachable from local refs at base `70c81c1`, the candidate
worktree, and the private `tadteo/Metis` GitHub repository. This is a privacy and
attribution review for a source-code preview, not a security certification or
scientific-capability evaluation. No repository visibility was changed.

## Source and history

- The current-tree public-file scanner and its self-test passed. A separate read-only
  pass over 463 reachable commits inspected 1,761 text blobs and flagged one old
  literal assignment in `tests/test_process_view.py:57`. That line is labelled
  `public fixture`; its value does not match the scanner's known provider-token
  patterns. No value was printed or copied into this report. No private filenames
  or personal home paths were found in the reachable text history.
- The history includes 55 image blobs at `.png` paths: 45 tracked now and 10 retained only in earlier
  commits. All 55 were viewed in contact sheets and checked with OCR for likely
  credentials, home paths, email addresses and non-loopback IP addresses. Across all 55
  images, detected addresses were loopback or example values. The four
  tracked SVG terminal captures are text and were covered by the text scan.
- Image metadata contained no creator, comment, location or similar identifying
  fields. OCR and metadata checks are heuristic; visual inspection found no private
  research records or credentials in the captures.
- The [ScholarPeer notice](../../src/autoresearch/assets/scholarpeer/NOTICE.md)
  preserves attribution and CC BY 4.0 terms for bundled prompt excerpts. The
  [Ponytail license](../../src/autoresearch/assets/ponytail/LICENSE) accompanies
  its bundled upstream skill. The repository carries Apache-2.0 for Metis code.

## GitHub surface

At inspection the repository was private, with no issues, pull requests, releases,
wiki, discussions or Pages site. GitHub Actions was enabled. Three prior workflow
runs failed before creating jobs; they are not evidence that the candidate passed
CI. The candidate's 44 base commits were still local to `main` at inspection.

## Interpretation

The audit found no concrete private-content blocker in the candidate history.
The built-in scanner is a guardrail, not comprehensive data-loss prevention;
changing repository visibility still requires a final review of the exact pushed
refs and GitHub settings. The public preview must retain the README's synthetic-demo
and unmeasured-autonomy limitations.
