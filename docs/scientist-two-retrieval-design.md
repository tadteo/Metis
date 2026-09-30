# ScientistTwo-informed retrieval design

Reviewed 2026-09-30 against code base `29ee3cb` and the
[representative journey](evidence/representative-journey.md). This is a proposed
engineering treatment, not an implemented fix or a measured capability improvement.

## What the primary sources establish

ScientistTwo separates limitation extraction and verification, ranks seeds by novelty,
and evolves ideas using successful and failed traces. Full-history evolution does
not prescribe whole-state serialization in every prompt.
[§3.1](https://arxiv.org/html/2609.19644v1#S3.SS1),
[§3.3](https://arxiv.org/html/2609.19644v1#S3.SS3).

Its two Google-retrieved papers concern novelty, not all retrieval. Limitation
verification permits sixteen rounds. Metadata bounds, deduplication, query planning,
caching and dollar-reservation recovery are unspecified.
[Appendix A.2](https://arxiv.org/html/2609.19644v1#A1.SS2).

Across 33 NeurIPS-derived tasks, reported averages are 2–3 days and USD 3,765,
including tokens and virtual machines, unlike our USD 5 model-only diagnostic.
[§4.3](https://arxiv.org/html/2609.19644v1#S4.SS3).

The [official project](https://scientist-two.github.io/) publishes papers, a demo,
and integrity results. The [official GitHub account](https://github.com/scientist-two)
shows one public repository; its [website repository](https://github.com/scientist-two/scientist-two.github.io)
contains `generated-papers`, `static`, `index.html`, and a license. No executable
orchestrator or exact orchestration prompt pack was located on these inspected
surfaces. This bounded audit cannot establish that no other release exists. We
cannot claim the authors solved our specific failure with an unpublished algorithm.

## Local evidence and the immediate mismatch

The journey stopped before a limitations provider call: a 654,640-byte prompt
needed USD 8.334900 reservation against USD 4.098618 remaining. Twelve Crossref
titles totalled 301,623 characters, including irrelevant journal contents. Records
appeared twice. Deduplication alone still required USD 4.531224; bounding displayed
titles to 500 characters in both copies reduced the offline reservation to
USD 1.136460. That cutoff was a diagnostic contrast, not a production choice.
Removing full text changed nothing because it was empty. Retry reduction was also
diagnostic only. [Recorded evidence](evidence/representative-journey.md).

The code explains the exposure. `extract_limitations()` in
[seeds.py](../src/autoresearch/research_stages/seeds.py) always searches the title
plus 1,000 objective characters, then embeds results while also adding them to
state. [memory.py](../src/autoresearch/memory.py) supplies broad state context;
[review.py](../src/autoresearch/review.py)'s `retrieval_model_view()` removes
recognized transport payloads but leaves long metadata. Separately,
[coding.py](../src/autoresearch/coding.py)'s `_context()` sizes raw observations
before [agents.py](../src/autoresearch/agents.py) projects them. Projecting first
retained all eight recorded intake steps within 59,323 characters in the offline
contrast. Whether that reduces live repetition remains unmeasured.

## Proposed implementation slices

**1. Bound presentation in one shared evidence module.** Extend the existing
schema-aware projection into a small shared interface used before history selection
and final request accounting. Preserve complete originals and hashes; emit one
canonical evidence entry per ID, with stage lists referencing it. Bound title and
metadata display separately from supporting passages. Record original length,
omission reason, source locator and projection version. Preserve arbitrary
scientific fields named `record` or `raw_response`; never apply indiscriminate
recursive truncation. Flag pathological metadata for inspection instead of treating
its shortened prefix as a credible paper title.

Apply the same view to nested history and define behavior for one oversized latest
observation: retain a bounded observation index and explicit omissions, rather than
allowing it to consume the history allowance. This changes presentation, not saved
checkpoints, scientific outcomes or failed-attempt retention. A 2–4 hour timebox is
reasonable only for this narrow projection/order slice and focused regressions;
it is not an estimate for the complete design or scientific validation.

**2. Reuse grounded intake evidence and search for gaps.** Replace unconditional
limitations retrieval with explicit coverage needs derived from the grounded brief:
reference method, task, datasets, known method mechanisms and unresolved limitations.
Reuse inspected intake passages when relevant and within the registered cutoff.
Persist why each source was selected. A missing issue should trigger a focused
query, such as a method phrase plus a limitation concept, with bounded provider
variants and recorded relevance decisions. Avoid concatenating the entire inquiry.

[literature.py](../src/autoresearch/literature.py) currently joins arXiv query words
with AND; long prose therefore overconstrains retrieval. Test short, safely escaped provider-specific
queries, exact identifiers, synonyms and controlled relaxation; preserve injection
defenses instead of admitting arbitrary query operators. Repeated
HTTP 429, empty results and irrelevant records must remain distinct outcomes.
Extend the existing in-memory cache policy with explicit query, provider, cutoff
and retrieval-time provenance, plus bounded retry/backoff. Caching does not certify
freshness or completeness. Existing identity merging already handles bibliographic
duplicates; the proposed prompt change removes repeated payloads across contexts.
Provider-ordered selection also needs relevance checks before its result limit.
This is a local proposal, not a recovered ScientistTwo policy.

**3. Make omitted content usable before relying on it.** Durable IDs alone do not
give every agent a retrieval tool. The present limitations panel has no evidence-read tool and cannot
page through evidence on demand. The minimal slice must supply sufficient selected
passages directly or return an explicit evidence gap. A later slice can introduce
bounded evidence reads through role/schema/tool contracts, with persisted requests,
passage offsets, hashes, errors and checkpoints. Evolution should retain an index
covering every attempt, including negative traces, and access to underlying records;
validate that selection does not suppress contradictory evidence. Keep held-out
review isolation intact. Recovery must use the normal engine and pinned behavior
configuration, not silently rewrite the stopped run.

**4. Preserve budget and scientific decisions.** Measure the final projected request
before reservation, expose input/output/retry components, and use the existing
reservation path unchanged. If sufficient evidence cannot fit, checkpoint an
honest budget/evidence block. Do not lower retry coverage, increase the cap, remove
critics or reinterpret missing evidence as acceptance. Preserve the existing
three-independent-inspectable-source novelty gate in
[config.py](../src/autoresearch/config.py) and `novelty_coverage()`; retrieving two
papers elsewhere is no reason to weaken it. Source count alone still does not
establish relevant coverage or novelty.

## Validation and limits

Use public synthetic adverse fixtures: enormous titles, duplicate identities,
nested transport, arbitrary scientific keys, one oversized observation, provider
throttling, zero hits, off-topic results and missing passages. Assert bounded final
requests, unchanged raw hashes, recoverable omissions, stable resumption, unchanged
reservation enforcement and rejection of insufficient coverage. Existing literature, review,
coding, accounting and fidelity suites are the starting points. Compare relevance
against a small independently labelled source set; measure supported claims as well
as bytes. Software tests alone establish neither scientific grounding nor quality.

After implementation and review, register a separate live treatment with the same
task, model, USD 5 cap and scientific settings. Record all failures, reservations,
source relevance and stage transitions. Passing limitations is an intermediate
outcome; require an accepted measured baseline before claiming improved end-to-end
progress. Keep the original diagnostic and its negative probes intact. Wider
scientific claims need additional tasks and repeated measurements. Writer
provisioning and the fixture's measured-reference versus published-reference
contract remain separate downstream uncertainties. No paid run, resume, runtime
change or fidelity promotion accompanies this note.
