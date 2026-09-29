# Literature identity and provenance

A DOI record and an arXiv record can describe the same paper. Literature merging joins all shared DOI, arXiv and URL aliases, and preserves those aliases through caching and saved evidence so subsequent searches cannot count the same paper again.

A merged evidence record has a new content hash and ID. Its `retrieval.identity_aliases` records the complete identity set; `retrieval.merged_sources` contains flattened original source descriptors, including their provider, URL, identifiers, content hash and retrieval provenance. `retrieval.content_source_id` identifies the record supplying the selected text. Exact provider response bodies and query metadata remain in search reports.

When a supplied reference duplicates an independently retrieved record, the independently retrieved text is selected. Longer supplied text cannot become independent evidence through this merge. An independent metadata-only lookup establishes a retrieved identity, but does not make supplied text independently inspectable. The novelty gate deduplicates identities before counting inspectable papers, including connections established by metadata-only bridge records.

Run `PYTHONPATH=src pytest -q tests/test_literature.py tests/test_review.py tests/test_agents.py`. These tests check evidence accounting; passing the minimum-paper gate does not establish exhaustive search or scientific novelty.
