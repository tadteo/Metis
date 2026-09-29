# Literature identity and independent provenance

Status: implemented, tested, independently reviewed and approved for commit. Base: reviewed `codex/analysis-reproduction` (`865edd7`).

## Requirement and defect

ScientistTwo novelty checks require actual retrieved comparisons; ScholarPeer §3.1 requires real search evidence rather than generated references ([primary source](https://arxiv.org/html/2601.22638v2#S3.SS1)). This task enforces the local minimum-independent-paper gate without claiming exhaustive novelty.

The pending main implementation merges DOI/arXiv bridge records but returns only the longest-content record. It drops other identifiers and source provenance. A later query can therefore count an arXiv-only copy separately from a DOI-only representative: two actual papers satisfy a three-paper eligibility gate. A supplied full-text record can also erase the independently retrieved version of the same paper.

## Plan and scope

1. Reuse the now-free isolated experiment-history worktree on `codex/literature-identity` from `865edd7`.
2. Import only the pending `src/autoresearch/literature.py` and `tests/test_literature.py` from main. Record captured hashes and explicitly credit these as inherited concurrent changes (gzip transport, uncertain dates, initial alias deduplication and tests), not newly authored history. Inspect configuration dependencies without replacing unrelated configuration.
3. Preserve merged identity aliases and source provenance through returned evidence, cache and cross-query accumulation. Keep independently retrieved content distinct from supplied content so supplied abstracts/full text cannot become independently inspected evidence.
4. Add regressions for two real papers remaining below the three-paper gate across queries/cache/serialization, independent retrieval surviving supplied duplicates, and metadata-only independent lookup not laundering supplied full text into novelty support.
5. Run focused retrieval/review tests, lint and type checks. Document behavior. Obtain independent root review before any implementation commit.

No edits to main, writer, review orchestration or coding integration are authorized by this focused task. The coordinator has the separate failed-review persistence finding. Exact response bodies and failures must remain available; canonicalization must not fabricate independent content.

## Imported snapshot

Main HEAD at capture: `0bdbd07`; selected files were uncommitted concurrent work.

- `src/autoresearch/literature.py`: SHA-256 `0d4dc066ddb43367fe94d17505af103b7c261c40585a32d21aa642b9c215a8db`
- `tests/test_literature.py`: SHA-256 `5eb4dd8988878cff9ce4aed38b56db47d92acfb5d58d8371a2de6f01a8a5dd5d`

The imported files use the existing LiteratureConfig interface and need no config changes. The optional `minimum` coverage argument remains backwards compatible.

## Implementation and validation

Canonical evidence now carries all connected identity aliases, merged case-normalized identifiers, the chosen content's source ID, and flattened original source descriptors. Each descriptor records its original content hash/provider/URL/identifiers/publication date/retrieval provenance. The canonical evidence receives a new hash/ID when its provenance changes. Repeat merges preserve the flattened descriptors rather than building recursive nested records. External retrieved content takes precedence over supplied content; supplied text is never relabeled as independently inspected. Exact query response bodies continue to remain in retrieval reports.

Coverage now canonicalizes before filtering for inspectable text: even a metadata-only bridge can establish that two abstracts belong to one paper. This closes a second demonstrated overcount through the same identity boundary.

Regression evidence: the cross-query/cache/JSON-serialization case failed with 3 independent papers where only 2 exist; both supplied-content cases failed because the returned provider was `supplied`; the metadata-only bridge case failed with 3 inspectable papers where only 2 exist. All four now pass. No network or paid model calls were used.

Validation:

- `PYTHONPATH=src pytest -q tests/test_literature.py tests/test_review.py tests/test_agents.py`: **42 passed** in 0.83 seconds.
- Focused Ruff formatting/check, mypy on `literature.py`, and `git diff --check`: passed.

The retrieval/reviewer/agent source audit against pending main also ran 55 existing tests successfully and separately identified failed-review retrieval persistence as a coordinator-owned follow-up. This task does not modify that boundary. Root independently reviewed the canonical union algorithm and provenance selection, found no blocking issues, and reran the 42 affected tests: **42 passed** in 0.72 seconds. Root approved the focused commit.
