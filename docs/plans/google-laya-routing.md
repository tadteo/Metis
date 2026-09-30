# Google Flash routing and Laya setup

Base: `cbdd55c`. User requested adding Google alongside the existing models and Laya
following the cost/quality routing discussion.

Implement an opt-in Google Flash profile shared by CLI and web settings. Keep the
primary provider for coding, experiment design, critical scientific judgments and
final review; route named routine roles to Google through its documented compatible
endpoint. Preserve existing explicit role providers, panels and adapters. Profile
application edits configuration only and must not start research or call a service.
Expose Google credential access and Laya's enable/endpoint/model controls in Model
access. Laya stays optional typed advice; no scientific call or evidence gate may be
skipped. Share credential-vault resolution with the existing provider transport.

Google source: https://ai.google.dev/gemini-api/docs/openai and pricing (2026-09-30).
Laya source: https://github.com/NandhaKishorM/laya and docs/laya.md. Token prices are
editable estimates; use dated published rates in the profile and explain their expiry. No claim
of scientific quality or cost parity is justified by these changes.

Acceptance: profile routes are executable, custom overrides and project settings
survive, Google and Laya credentials never enter configuration, Laya failures retain
normal reasoning, and no setup action incurs a model request. Check UI edits and
saved settings, desktop/narrow light/dark rendering and keyboard access. Validate
focused provider/routing/settings/web/Laya suites, all required repository checks,
independent review, feature commit, fidelity documentation, merge and affected checks.

## Evidence

Read-only search initially failed because
an unmatched zsh glob referenced a nonexistent console path; corrected to actual
static assets. No code, experiment or credential was affected.

Initial browser run passed the 62 existing tests. New coverage then found a test-fixture error (question input was lazily created); initialized the fixture and reran. Ruff initially could not create its cache in the managed worktree under sandbox permissions; reran with `--no-cache`.

Focused Python check: 145 passed, 1 failed. The pre-existing non-ASCII credential
test used an environment dummy but the host vault took precedence; its unmocked
transport unexpectedly completed a real provider request with only synthetic
`Return JSON` / `Check` text. There is no retained provider billing receipt, and
no research measurement resulted. The user was informed. Added suite-wide null
vault/session isolation, removal of inherited API-key environment variables and
an HTTPX transport guard against external hosts (MockTransport and loopback
fixtures remain available). Credential tests explicitly supply synthetic backends.
This closes the observed test isolation gap before any further full-suite run.


Final validation: 164 focused Python tests passed; full suite 913 passed, 3 skipped
in 294.86 seconds; 67 browser tests passed; Ruff lint/format, mypy (73 files),
47-agent/28-stage specification validation, public scanner and scanner self-test
passed. Wheel built and installed-artifact test passed (1 test). Offline demo
completed with previous best retained after nonsuperior meta refinement.
The new race regressions initially needed one lazily created fixture node, then
passed. Independent review found one P2 credential destination race; resolved
and re-reviewed with no remaining findings (see review record).

Browser evidence used a disposable localhost state with zero research runs:
Google profile applied without model calls, selected Google credentials, Laya
expanded, settings saved and survived reload. Desktop and 390×844 light/dark
screenshots are under docs/evidence/google-laya-*.png. Keyboard traversal revealed
footer overlap on narrow screens; scroll padding fixed it and both themes were
rechecked with the Laya address focused. No live Google/Laya endpoint or research
quality/cost evaluation was run. The earlier unintended synthetic provider call
is recorded above, separately from offline validation.
