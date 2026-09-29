# Final console lifecycle and artifact reconciliation

Base: `f63e123`. Final comparison against concurrent main `87bf703` found an omitted
textual MIME guard and binary-download regression, plus missing artifact versions,
bounded-read, cross-run and path-escape fixtures. Restore those without weakening the
shared descriptor-based Store reader. Generic accounting fixtures already supersede
main's writer-specific accounting tests.

The web console also inherited daemon research workers: closing the HTTP server could
exit during a paid request or experiment. Make shutdown stop accepting execution,
request pause for all workers, and join them at their existing safe checkpoints before
returning, preserving all receipts and reservations. Cover normal shutdown and an
HTTP-server failure; avoid inventing another scientific execution controller.

Own only web.py, focused web/Store security tests and this plan/review record. Preserve
current token/origin checks, per-run exclusivity, archived behavior API, and existing
research lifecycle. Run focused pytest, Ruff, mypy and public scan. Obtain independent
coordinator review before separate coherent lifecycle and artifact commits.

## Evidence

The PDF MIME regression and all three lifecycle exits (normal listener return,
KeyboardInterrupt, listener exception) failed against the base. After the fix, 48
web/Store-security/CLI tests pass. Strict web mypy, Ruff, public-content scanning and
`git diff --check` pass. The coordinating agent independently reviewed and approved
the complete source and test diff before commits. No model calls or live experiments
were used; synthetic worker checkpoints test lifecycle ownership only.
