# Independent review: provider availability fallback

Reviewed against 804c33b by fallback_review; approved after correction.

Verified shared monetary/call budgets, frozen permitted models, independent failed-call
accounting, actual-model cache provenance, bounded alternatives, cooldown, pause and
inline page preservation. Independent focused runs passed 54 transport/inventory/
fallback tests and 63 agent/cache/projection/catalog tests. A socket-bound endpoint
check required the implementer's unrestricted test environment. Browser file suite:
95 passed, including inline notice/control preservation.

Finding resolved: artifact selection inheriting a held-out role originally checked
only its own role's context/model policy. It now protects the original role too.
An implementer-discovered regression also showed protected frontier errors bubbling
back into ordinary fallback; the protected boundary now makes those errors terminal
to its caller, without rewriting the recorded failed transport receipt. Regression
checks cover both paths, commands, cooldown expiry and pause during an in-flight call.

Actual production-page synthetic preview checked at desktop and 390px widths in
cream/charcoal. Notice wraps without hiding navigation, summary or controls. No new
keyboard control was introduced. Scientific gates, prompts and comparison models
are unchanged. This review does not establish equal scientific quality across models
or live provider access. Existing pinned research is not migrated automatically.

Post-merge independent follow-up approved the test-only timestamp correction needed
by concurrent timer integration. All 20 fallback cases passed independently; the
implementer recorded 133 integrated Python and 103 browser checks passing.
