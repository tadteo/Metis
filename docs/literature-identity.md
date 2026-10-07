# Literature identity and provenance

A DOI record and an arXiv record can describe the same paper. Literature merging joins all shared DOI, arXiv and URL aliases, and preserves those aliases through caching and saved evidence so subsequent searches cannot count the same paper again.

A merged evidence record has a new content hash and ID. Its `retrieval.identity_aliases` records the complete identity set; `retrieval.merged_sources` contains flattened original source descriptors, including their provider, URL, identifiers, content hash and retrieval provenance. `retrieval.content_source_id` identifies the record supplying the selected text. Exact provider response bodies and query metadata remain in search reports.

When a supplied reference duplicates an independently retrieved record, the independently retrieved text is selected. Longer supplied text cannot become independent evidence through this merge. An independent metadata-only lookup establishes a retrieved identity, but does not make supplied text independently inspectable. The novelty gate deduplicates identities before counting inspectable papers, including connections established by metadata-only bridge records.

Run `PYTHONPATH=src pytest -q tests/test_literature.py tests/test_review.py tests/test_agents.py`. These tests check evidence accounting; passing the minimum-paper gate does not establish exhaustive search or scientific novelty.

## Query kinds and transient provider failures

`Literature.search_external(query, count, kind)` distinguishes exact lookups from topic search. `kind="title"` (default: citation audit in `references.py`, official-writer task foci and targeted hints, review queries) sends the text exactly as written. `kind="topic"` (`Literature.search_topic`, used by limitation extraction and every novelty query) lets the built-in providers send at most eight salient terms; arXiv receives three required terms plus an optional `OR` group. A topic with no salient term is sent raw and the report records that limitation. Reports keep `query`, `query_kind`, `keyword_query` and each provider's exact `provider_query`.

Every `search_external` caller, including citation audit, now retries HTTP 429, 5xx and transport failures at most three times per provider. The wait is `Retry-After` (seconds or HTTP date, clamped to 60 s), with exponential backoff (2 s, then 4 s) as the floor when the header is absent, zero or past. The worst-case added wait is 120 s per provider, or 360 s per cited reference with the three default providers. Each attempt is recorded in `providers[].backoff`. Callers get no attempt override: previously a transient throttle immediately left a citation unverified and blocked approval, and a fixed, recorded bound keeps the retrieval interface and its provenance uniform. The official-writer throttle applies the same policy and Literature does not retry inside it.
