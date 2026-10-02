# Prompt cache reuse review

Base: 88b2c6f. Isolated branch: codex/prompt-cache-reuse.

The independent reviewer review_prompt_cache found that merely moving reference
fields earlier within one JSON user message did not satisfy xAI's documented
whole-message prefix reuse. Resolved with a stable reference message, ordered
chunks of eight evidence records, and trailing current context. The versioned
common prompt specifies lossless assembly and evidence ordering. A second offline
comparison showed that a single reference message still changed when papers were
appended, motivating the evidence chunks rather than removing research content.

Re-review approved: no actionable correctness, privacy, scientific-preservation or
accounting findings; 82 independent focused tests passed. The reviewer's initial
command referenced nonexistent tests/test_memory.py; the corrected command passed.
No reviewer edits or paid calls.

## Diagnosis and checks

The synthetic real-AgentRunner regression initially failed with only 382 shared
characters before a 50,000-character reference after feedback/counters changed.
The xAI HTTP regression failed because the conversation-affinity header was absent.
Initial fixture mistakes (missing Evidence.url, then an invalid role output) were
corrected before interpreting those failures. A version-bump helper initially
assumed integer-only versions and failed on a dotted version; fixed before testing.
Ruff then found an unsorted local test import, which was corrected.

A read-only local replay compared 31 successive saved same-role/model/system
requests from limitations and verification. Only 9 pairs had identical complete
reference context when evidence was kept in one message. Evidence changed in the
other 22 pairs, always by appending to the previous sequence. With ordered chunks,
the median identical whole-message prefix is 595,092 characters, median request
length 687,028 characters, and median reusable fraction 86.62% (minimum 79.47%).
These are character-prefix eligibility measurements, not token cache-hit rates,
provider receipts or dollar savings. Private requests remain outside this repository.

75 focused tests passed after the final chunking change. Lossless reconstruction,
feedback freshness, appended and corrected evidence, local response-cache identity,
shared reservation/settlement bounds, JSON/SSE receipts, missing retry receipts and
historical unknown cache counts are covered. Existing held-out, redaction and repair
checks remain required in the full suite. Static checks, 48-agent specification
validation and 106 browser tests passed. Full release results are recorded below.

## Limits

Provider caching remains opportunistic. No paid request was sent and no research
run was restarted. Monetary accounting remains conservative configured-rate usage;
cached receipts do not silently apply a price discount or rewrite historical charges.
This change demonstrates transport behavior, not scientific parity or measured
research-quality/cost equivalence. Existing runtime-pinned runs need explicit linked
continuation to adopt the changed prompt bundle.

The wheel build and installed-artifact smoke test passed (1 test). Public-file scan
and scanner self-test passed. Synthetic demo completed with outcome
previous_best_retained_meta_refinement_not_superior and no error. All active worktrees
were inventoried before integration; only this task's checkout had uncommitted edits.

Final complete regression suite: **1093 passed, 3 skipped in 323.80s**.
No skipped external/release check is claimed as passed; installed-wheel smoke was
run separately and passed.

Post-commit fidelity synchronization initially used the wrong script name
(scripts/update_fidelity.py); that command failed and the following matrix check
correctly failed on unsynchronized assets (1 failed, 16 passed). Running the existing
scripts/update_fidelity_report.py regenerated the artifacts; all 17 matrix tests and
the public-file scan then passed. No failed check is represented as successful.
