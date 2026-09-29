# Guided setup triage

Base: `d2e12fb`. The reported setup screen displays dependent errors as separate
demands and repeats a malformed credential reference in writer diagnostics. The user
wants Metis to investigate what it can, choose safe next actions, and ask only for
information or host changes that require a person before research starts.

Boundary: keep the existing server-side readiness and research gates. Add a shared
triage projection over preflight results; make the web review lead with one actionable
next step and progressive disclosure, automatically perform bounded read-only source
inspection when the source exists, and direct users to the existing separately
budgeted AI preparation for evidence-backed proposals. Never execute project code,
install tools, pull images, make paid calls, invent SOTA values, or accept an evaluator
during checks. Keep complete diagnostics available. Redact malformed credential
references in all readiness surfaces, including writer checks.

Acceptance: missing source masks dependent questions; source inspection shows command
candidates without claiming they are verified; provider/host changes and original
benchmark values are asked explicitly; later manuscript prerequisites are deferred;
no raw credential-like string appears in readiness; prior validation still invalidates
on edits and creation remains blocked until all hard checks pass. Verify with focused
Python and browser tests, full relevant repo checks, synthetic UI walkthrough in both
themes and narrow/desktop layouts, independent review, commit and merge.

## Evidence and review

Three focused Python regressions first failed on missing guidance and credential
disclosure; the writer warning repeated the malformed reference three times. The
final focused suites passed: 31 Python setup/onboarding tests and 41 browser logic
tests. Ruff lint/format, mypy (69 modules), specification validation and the public
file scanner passed. The offline synthetic demonstration completed. None of these
checks makes a paid call or establishes scientific parity.

Visual walkthrough used a disposable local server and synthetic project files under
`/private/tmp`. Dark and light desktop layouts and a 390px narrow viewport showed
readable action cards without horizontal overflow. Keyboard Check setup opened the
review and the source action returned focus to the source field. With no source, the
review showed folder, provider and Docker actions; with a synthetic source it showed
unverified train/evaluator filename candidates, the original benchmark request and
host actions. No project command or provider call ran. Browser UI automation via
pointer clicks did not consistently activate controls in the test browser, so the
changed journey was exercised by keyboard and separately by the browser logic tests.

An initial full-suite attempt without local socket/process permissions finished with
798 passed, 3 skipped, 13 failed and 56 errors. The server errors were socket-bind
denials; remote/writer process tests were similarly denied. This was a validation
environment failure, not a passing suite. A second full run with local permissions
passed: 868 tests passed, 3 skipped in 266.77 seconds. The later small browser-only
retry-card edit passed all 41 browser tests; Python focused tests passed 31/31.

Independent review found incorrect source-error wording, hidden inspection failures,
a nonfunctional retry, an Advanced-link routing issue and a stale review card after
retry. Each finding was fixed and covered by a focused regression where applicable.
The final independent pass reported no remaining actionable finding; see
`docs/reviews/setup-guidance.md`.

Merged as `5df0f24` after feature commit `681e014` and fidelity documentation
commit `af84fee`. Post-merge checks: 48 focused Python tests, 41 browser logic
tests, 2 authenticated HTTP integration tests, Ruff lint and the public-file
scanner passed. The main checkout was clean before and after integration; the
older detached onboarding review checkout retained its unrelated changes.
