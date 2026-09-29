# Plotting provenance review

Reviewer: workflow_review; implementer: root. Root independently ran the eight regression tests.
The reviewer exercised the real pinned archive and source: 1,097 files verified; mutation of
plot/ref.json was rejected. The review found a macOS /tmp alias compatibility issue. Resolving
the configured root while checking only descendant symlinks fixed it; regression retained.

Expected hashes are derived from the checksum-verified archive on reuse, rather than trusting
an editable installation receipt. The source checkout must be clean at its pinned revision;
style files must be tracked. Snapshots have an exact file set and matching bytes. The archived
provenance excludes images but records all source/data revisions and consumed file hashes.

Evidence: tests/test_plot_assets.py (8 passed), tests/test_writing.py archive safety tests,
and actual pinned archive validation. This is asset provenance evidence, not a generated-paper
quality evaluation. No paid model call was used.
