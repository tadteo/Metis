# Typed advisory and writer instruction review

Base: `34e3395`. Scope: catalog/routing, Laya typed transport and call receipts,
writer evidence guidance, and the associated contract tests.
Independent reviewer: coordinating root agent, before commit.

## Findings and resolutions

- The live typed question is now an explicit `laya_triage` definition with a real
  non-generative transport, configured Laya model policy and `LayaDecision.v1` schema.
  Its rendered prompt is the actual typed-question JSON. Declared advisory callers
  still execute their scientific reasoning agents; advisory output cannot promote evidence.
- Request, question, definition, catalog, schema and run-bundle identities accompany
  started/completed/cache/failure events. Prompt revisions invalidate cache entries;
  the privacy cache setting and redaction apply to this transport too.
- The reviewer questioned whether oversized state was truncated after hashing.
  Source inspection verified this was **not a bug**: oversized state already refuses
  the call without truncation. The shared envelope builder and captured-HTTP regression
  now establish payload/hash equality and preserve refusal, full evidence and zero
  transport cost when a request cannot be submitted.
- Writer evidence-reporting instructions are a catalogued Markdown artifact, distinct
  from official upstream writing prompts. Materialization records the guidance hashes,
  honors custom catalogs, and includes the catalog identity in the resumable invocation.

The independent reviewer approved these changes after examining the final diff.
94 focused agent/catalog/Laya/writer tests passed. Ruff and strict mypy passed for
the modified implementation. These software fixtures do not establish research-quality
parity or live service availability. The separately reviewed evaluation task-template
follow-up is recorded in its own review.
