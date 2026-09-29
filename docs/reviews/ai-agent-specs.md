# AI agent specification review

Base: `9cd457d` (pre-implementation architecture audit and plan).
Scope: external prompt and agent artifacts, catalog validation, model routing,
specialist dispatch, role output contracts and invocation provenance.

Independent reviewer: coordinating root agent. Review occurred before these
implementation commits; it did not rely only on the implementing agent's checks.

## Findings and resolutions

- Preserve official PaperOrchestra model slots (`writing_writer`,
  `writing_reflection`, `writing_plotting`). They are now declared in model policy
  and allowed only in provider overrides; they cannot masquerade as local agents,
  prompt overrides or command handlers. A regression test covers this distinction.
- Experimental plans previously required only a question. Accepted ablation and
  rebuttal plans now require nonempty ID, question, intervention and expected
  evidence, with optional metric and control requirements. ScholarPeer question
  plans retain their separate schema. The rendered role schema exposes this rule.
- Custom tool declarations must be enforced. Tool IDs retain their trusted action
  and permission; coding/inspection output validation intersects the step agent's
  capabilities with its original scientific role's capabilities.
- Live writer instructions come from pinned upstream agents. Writer definitions
  explicitly identify upstream prompt scope, revision and the limited purpose of
  the local demo/adapter prompt; the official writer remains intact.
- Coding must receive its original scientific instructions. The coding session
  now gets the rendered role instructions, including operator overrides, alongside
  the tool protocol; the session identity binds those instructions.

The coordinating reviewer reported no remaining blocking findings in this owned
scope. Final integration review remains responsible for the run behavior bundle,
held-out state projection and UI interpretation of upstream model selection.

## Validation

- 91 focused tests passed: agent catalog, specification-driven invocations,
  independent panels, architecture, iterative coding, inspection and review.
- Ruff passed for all modified source and test files.
- Strict mypy passed for all nine modified/new source modules.
- The two stale writer architecture fixtures now return the actual upstream
  `(manuscript, references)` contract with substantive synthetic manuscripts.
- Other existing invocation fixtures now supply the accepted payloads their roles
  actually require; their original routing/aggregation/privacy assertions remain.

These are deterministic software checks. They do not establish model quality,
research novelty, scientific parity or live upstream service availability.
