# Ponytail coding policy and paired pilot

Base: e6bee9f. User requested using Ponytail and testing cost reduction without
compromising quality. Upstream: DietrichGebert/ponytail revision
 e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156 (MIT).

Scope: adapt its reuse-first/minimum-sufficient implementation guidance into the
versioned coding-step instructions only. Preserve structured output, scientific
requirements, meaningful tests, protected evaluation, reproducibility, independent
criticism, negative evidence and all existing runtime gates. No global plugin hooks,
model routing changes or weaker testing policy. Attribute the adaptation and license.

Compare the original prompt with the adapted prompt through the real accounted
coding loop using identical configured model, fixture, limits and fresh workspaces.
Task: aggregate public synthetic experiment CSV records with correct statistics,
failed-attempt retention and strict input checks. Freeze an independent acceptance
suite before calls; evaluate exported code separately. Register attempts before
execution and retain prompts/hashes, outputs, errors, checks and usage privately.
Three pairs, alternating order, maximum $0.50 accounted model cost per attempt
($3 total), no frontier or cache. Report all attempts and failures. Dollars are
configured-price estimates, not invoices. One fixture cannot establish general
non-inferiority or scientific capability. Adopt as default only if pilot preserves
quality and improves aggregate cost; otherwise retain an opt-in experiment.

Validation: focused coding/spec/behavior/evaluation tests, full required CI checks,
independent agent review against base, fixes, feature commit, fidelity evidence update,
merge and clean-tree verification. Report external blockers precisely.

Initial access checks: sandboxed read-only SQLite inspection could not open settings;
sandboxed git ls-remote failed DNS. Approved escalated retries succeeded. Credential
availability verified without logging secrets or altering settings. Available model
references: grok-4.7 and gemini-3.8-flash; choose the cheaper configured Flash for both
arms. Availability is not yet a successful API call.

## Preserved execution and review observations

Pinned upstream download through the system Python failed certificate verification;
retried successfully with the project's httpx/certificate bundle, without disabling
TLS checks. Initial lint found late-bound callback loop variables; replaced the
callback with functools.partial before live execution. Offline wheel build against
an empty temporary cache failed to resolve hatchling, and its dependent installed
wheel test failed because no wheel existed. Retrying with the existing cache built
and passed the installed artifact test.

Automatic approval initially rejected a live pilot over possible private project
export. A network-free captured request verified only the synthetic fixture,
empty research state, public instructions/defaults, and no secrets or home paths.
The reviewed retry was approved. Subsequent review additionally reset the complete
project object, references, resource hosts and data mounts for future invocations.

The first six Flash attempts returned HTTP 503 errors; one had an earlier valid
list action. Their conservative usage reservations are not observed generation or
confirmed invoices. Review found the outage stop had tested token count even though
unknown usage is deliberately estimated nonzero. Fixed to stop on ProviderError and
preserve per-call estimate flags. The separate Grok battery stopped after its third
attempt's transport timeout; earlier attempts violated the one-action JSON contract.
All earlier attempts and later unattempted registered slots remain represented.

A final separately registered one-pair single-response probe uses the same fixture
and independent acceptance suite, with an explicit single-response role in private
spec bundles. It bypasses iterative tools and cannot establish coding-loop success.
No prompt or task tuning from acceptance failures. All trial caps together remain
below the announced $3 ceiling. The default-adoption gate remains unmet without
successful full coding-loop quality and cost evidence.

Independent reviewer /root/quality_review also required proof all acceptance tests
ran (zero exit alone could falsely pass on early exit), and evaluation of only the
specified self-contained summary.py. Both fixed; offline checks cover a correct
reference, incorrect population standard deviation, early exit and provider outage.

## Final disposition and validation

No live task completed. The separately labelled single-response baseline also timed
out; its Ponytail arm remained unattempted. Total conservative accounting was
$0.58776: $0.17319625 at configured prices from reported tokens, $0.41456375 for
unknown-usage reservations. No scientific-quality or savings claim is supported.
Kept default agents.json byte-identical to base, with an optional packaged policy and
prepare_specs helper for explicit new studies. No installed global plugin or changed
user settings. Public results are under evaluations/ponytail; full private attempts
are archived in the main checkout's ignored .autoresearch/ponytail-20261001 directory.

Full suite: 1001 passed, 3 expected skips before final opt-in/scorer refinements.
Affected followup: 49 passed; final pilot suite: 6 passed. Independent reviewer reran
all six and approved. Browser 98 passed, mypy 83 files, Ruff lint/format/spec validation,
wheel install, scanner/self-test and synthetic complete demo pass. Final review also
fixed reads from live instead of frozen evaluation fixtures. A sandboxed Ruff cache
write failed once; --no-cache recheck passed. No live result was deleted or promoted.

## Integration with concurrent main changes

Main advanced to 3649af4 while this task ran, adding independently reviewed bounded
evidence context and incrementing agent versions. Inventory found no uncommitted
worktree changes. Integrated main without altering its runtime changes. The sole
conflict appended different sections to docs/coding-harness.md; retained both.
Changed prepare_specs to retain the current baseline version and suffix the enabled
version with +ponytail.1 instead of hardcoding historical versions 3/4. Historical
live evidence remains explicitly bound to e6bee9f and its original prompt hashes;
no claim is made that those measurements evaluate the later context implementation.

Integrated focused checks: 76 passed; types/lint/format/specification, installed wheel
and synthetic demo pass. Full integration suite reached the fidelity ancestry check
before the merge was committed and rejected b15484d (present in MERGE_HEAD but not
HEAD). Focused reproduction confirmed this exact cause. Finish the reviewed internal
merge commit, then rerun the affected ledger checks; no scientific guard is relaxed.

Final integration outcome: full suite 1013 passed / 3 skipped / one pending-merge
ancestry failure; after merge commit 58fe54b, final fidelity+pilot 23 passed. Types
84 files, lint/format/specification, integrated wheel and complete synthetic demo
pass. Independent reviewer approved integration and the ledger-only change. Final
scanner/self-test pass. Feature 82f8de8 is linked in the actual fidelity ledger.
