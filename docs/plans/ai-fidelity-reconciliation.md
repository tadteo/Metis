# AI architecture and concurrent scientific repair reconciliation

Status: implementation and independent review in progress.

The architecture task began from the actual dirty checkout, preserved honestly in
`92a9ace`. Concurrent scientific repair continued separately and was frozen for this
port at `aeb24aa`; the other integration subsequently completed on `main` at `87bf703`.
Do not replace those scientific repairs with the earlier working-tree snapshot.

## Ownership and acceptance

- Writer adapter: retain stage request failures, recover process groups/containers
  before settlement, use durable idempotent reservation intent and verify plotting
  references against their checksum-pinned archive. Preserve catalog material prompts,
  held-out exclusion and generic subordinate accounting.
- Science handlers: retain interrupted experiment intent and uncertain outcomes,
  rejected refinement history, strict ablation attribution, incremental review evidence,
  canonical citation identities, inspector input identity and declared coding exports.
- Statistical evidence/evaluation: preserve units and reported precision, protect and
  reproduce registered paired analyses, retain original inputs, train-only preprocessing,
  failed variant denominators and negative attempts. Scientific statements do not become
  valid merely because they parse.
- Coordinator: preserve immutable artifact history, explicit setup errors, evaluation
  exit codes, all-settled writer migration checks, rich interfaces and published fidelity
  evidence. Integrate external statistical prompts into actual writer materials.

The graph retains A04's existing `peer_rounds` meaning: total assessments, including
initial assessment. Setting three allows two complete experimental rebuttal/revision
cycles; default two allows one. The paper's Section 3.5/Table 5 and Appendix A.2 leave
counting terminology ambiguous. Preserve the initial repository configuration contract
and document this interpretation instead of silently changing existing study budgets.
The later fidelity branch's counter reinterpretation is intentionally not ported.

Independent reviewers cross-check statistics and science scopes; the coordinator
reviews writer changes; another agent reviews coordinator and interface changes.
Keep focused commits, preserve failed checks in review records, and run the full suite,
public scan, type/lint checks, installed-wheel demo and pinned upstream offline tests
before completing integration. None of these software checks certifies live research
quality or reproduces the original benchmark performance.
