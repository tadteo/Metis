# GitHub documentation readiness

Source requirement: setup and usage documentation must be current, readable and
available on GitHub before the maintainer shares Metis on X and LinkedIn.

Base: `ca281094a5f3c5151517f9a401fae167c13c4271` (`main`). Task branch:
`codex/github-documentation`, in an isolated worktree. Existing plans for the README,
public release, provider presets and execution runtimes are historical context.
Other active worktrees, including social copy, are outside this task.

## Boundary

- Keep the README a clear first impression with a runnable offline quick start,
  scientific limitations and direct paths to setup, usage and advanced guides.
- Add a sequential installation/first-live-run guide and actionable troubleshooting.
- Refresh the documentation index and remove the duplicated stale execution section.
- Generate the CLI reference from the actual argument parser and check it in CI.
- Check first-party user/contributor documentation links, images and Markdown anchors
  offline in CI. Preserve historical plans/reviews and vendored upstream artifacts.
- Document the maintenance rule in contributing guidance and the PR checklist.

No runtime, interface, scientific contracts, provider defaults or dependency changes.
No paid API calls, scientific quality claim, new hosting service or recurring schedule.

## Acceptance and validation

1. A new visitor can install, run the synthetic demo, open its record and find the
   first-live-run prerequisites without searching implementation/history files.
2. All checked local links, image paths and heading anchors resolve. The committed
   CLI reference matches the current parser, including SSH subcommands.
3. From the branch's source and a fresh private temporary Store, run the documented
   offline demo and check the loopback console. Verify CLI help and idle inquiry
   creation without a provider call. Record real outcomes and any failed checks.
4. Test the documentation checker against broken links/anchors and stale generated
   output; run formatting, lint, types, specifications, tests, browser logic,
   public-file scanner and installed-wheel checks as applicable.
5. Obtain another agent's independent review against the fixed base; record findings
   and resolutions. Commit, merge without absorbing other work, publish to GitHub
   and verify CI on the published commit.

GitHub rendering evidence: inspect the README, index and first-run guide as rendered
Markdown, including headings, code blocks, navigation, screenshots and synthetic
labels. UI appearance/interaction is unchanged; existing screenshots are retained.

## Progress

- Main is clean and GitHub is public. The base's recent GitHub CI runs passed.
- Found duplicated old/new backend guidance in `docs/execution-options.md`; the README
  repeats setup and buries the reader in advanced material. No documentation CI gate
  or source-generated CLI reference exists.
- Initial worktree creation was blocked by the filesystem sandbox; the same authorized
  operation succeeded with escalation. Initial sandboxed GitHub reads could not reach
  the API; read-only escalated queries succeeded. These were tooling failures, not
  scientific attempts.
- Implemented sequential setup, troubleshooting, an expanded task-oriented index,
  a shorter README, generated CLI help and an offline documentation CI gate. Removed
  the duplicated obsolete compute introduction; current backend detail is retained.
- The first checker format check requested formatting; applied it and the check passed.
  An initial patch with repeated file operations was rejected before application and
  was rewritten as a valid update. No runtime/scientific files changed.
- Frozen dependency installation succeeded in the isolated environment. Sandboxed
  `uv run --no-sync` initially could not initialize its normal cache; using a temporary
  writable `UV_CACHE_DIR` resolved that tooling restriction.
- The first full-suite attempt was interrupted after 490 passes / five failures:
  PDF tests could not run `/bin/ps`, loopback bind was prohibited, and native Seatbelt
  could not nest under the tool sandbox. A normal-permissions full suite is running;
  those failures are retained as environment evidence, not described as passed checks.
- Offline demo: completed, 34 synthetic experiments. Loopback console worked after
  launching with normal permissions. Visually followed Settings, Add provider,
  Configure and New research without saving credentials or starting live work.
- Idle CLI inquiry smoke: missing credentials correctly refused creation; with a
  synthetic locally configured key and all HTTP forbidden, creation returned
  `ready` at `intake`, with zero HTTP requests. A first smoke assertion expecting
  `created` was corrected to match the actual idle status.
- Focused docs/CLI/package checks: 21 passed, one skipped. Installed wheel: one passed.
  Formatting (186 files), lint, types (91 source files), specification validation,
  documentation checker, public-file scanner and scanner self-test passed.
  Browser configuration logic: 109 passed. The writer provisioning module's help
  resolves in the installed uv environment; runtime downloads/paid work are untested.
- Independent review found three concrete setup gaps; all were fixed and rechecked.
  [The review record](../reviews/github-documentation.md) records approval and limits.
- GitHub's GFM API rendered the README, documentation index and first-run guide with
  expected headings, code blocks, tables and images. Actual published-page visual
  inspection and published CI remain to be recorded after pushing the candidate.
