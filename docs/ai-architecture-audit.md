# Pre-change AI architecture audit

Inspected 2026-09-29 against the actual dirty working tree, ScientistTwo
[2609.19644v1](https://arxiv.org/html/2609.19644v1), docs/paper-spec.md and every row
of docs/fidelity.json. This records findings before implementation. The original
checkout contained substantial uncommitted integration work after 0bdbd07; that
work is preserved separately and is not attributed to this refactor.

## Scientific coverage

| ScientistTwo capability | Concrete existing implementation | Architectural finding |
|---|---|---|
| Limitation extraction / independent verification | engine._advance, limitations/verify_limitations prompts, literature.search | Implemented with bounded feedback, but hidden in branch dispatch and strings. |
| Iterative seeds / novelty / ranking | engine._advance, novelty_coverage, AgentRunner panels | Prior candidates and retrieval preserved; role requirements and loop graph implicit. |
| Subset baseline reproduction | engine._experiment, coding.run_coding, Executor | Real measured execution exists; live coding omits baseline role instructions. |
| Subset implement / critic / engineer | engine, coding, decisions | Independent critic and numerical guard present; tool/runtime and science prompts mixed. |
| Full benchmark / critic / engineer | engine, protected evaluator and immutable protocol | Correct separate full comparator retained; large engine owns execution and science. |
| Evolution / unused-seed exploration | engine._finish_candidate and _advance | Success and diagnostic failure histories retained; scheduling/stopping rules implicit. |
| Best-candidate selection | engine select branch and AgentRunner critic panel | Full-benchmark gate exists; generic response schema makes selected_id optional. |
| Ablation planning / execution / critique | engine plans and experiment paths | Measured component interventions exist; plans are weakly typed dictionaries. |
| Full refinement / strict comparison / ablation re-entry | engine candidate_update, compare, comparison_origin | Incumbent preserved until measured improvement; nested transitions difficult to inspect. |
| Initial drafting / manuscript enhancement | writing, paper_orchestra and pinned worker | Official agents integrated; upstream dependency prompts intentionally remain upstream. |
| ScholarPeer review / experimental rebuttal | review, assets/scholarpeer, engine | Published templates attributed and hashed; reconstruction adapts retrieval and bounded rounds. |
| Meta-review / method re-entry / fallback | engine meta_review/meta_refine/compare | Implemented; limits and fallback state are buried in code. |
| Four integrity checks / seeded reruns | integrity, inspection, references, engine._final_integrity | Substantial evidence checks; separate claim roles need explicit contracts. |
| Held-out evaluation | engine._final_integrity, evaluation | Stored in reviews; reopening a completed run can leak it into optimization and writer materials. |
| Capability evaluation | evaluation, evaluations/, fidelity ledger | Real public-task protocol exists; paid autonomous research and original benchmark parity unmeasured. |

## Platform findings

1. **Agents are distributed constants.** prompts.ROLES, agents.CRITICS/CHEAP_ROLES,
   coding.CODING_ROLES, inspection.INSPECTION_ROLES and decisions.STAGE_DECISIONS
   independently encode identities/policies. AgentRunner combines specialist
   dispatch, routing, panel arbitration, schema repair, caching and billing.
2. **Instructions are implementation strings.** General scientific roles, common
   safety instructions, coding/inspection protocols and review adaptation cannot
   be reviewed/replaced as a coherent prompt pack. Live coding receives original_role
   but not its detailed scientific prompt. The empty WRITING_PROMPTS fallback is dead.
3. **Workflow identity is duplicated.** Stage enum, engine branch chain and web
   labels/phases are separate representations. Re-entry and negative outcomes need
   a graph consumed by dispatch/validation and exposed to contributors/operators.
4. **Outputs validate too late.** AgentOutput defaults most role-required fields;
   arbitrary plans/structured records are checked downstream. Add semantic contract
   fixtures without treating schema validity as scientific approval.
5. **Runs do not pin behavior.** Config/source are archived, but current installed
   prompts are used after resume. prompt_sha256 is actually a cache identity; repairs
   change request text without a distinct content hash. Freeze behavior and distinguish
   definition, prompt, request and runtime provenance.
6. **Runtime seams need cleanup.** Private filesystem/process helpers are imported
   from execution across modules. Generic Store accounting understands writer child
   calls. Memory is durable but heterogeneous; retain original records when adding
   typed projections. Do not discard negative evidence during context selection.
7. **UI/CI need a shared system view.** TUI shows raw JSON and web duplicates stages.
   tests/test_web_ui.mjs is not run by CI. Prompt assets need an installed-wheel check.
8. **Scripts are not the core problem.** The only scripts/ utility, scan_secrets.py,
   is used by CI. Do not delete useful tooling for appearance. Embedded benchmark,
   evaluator and Slurm programs should become normal inspectable source assets.

## Design choice

Keep the real provider, executor and Store interfaces: they already enforce CAS,
leases, private immutable artifacts, conservative reservations, sandbox policy and
protected evaluators. Add one packaged specification layer for AI behavior and
small validated loaders/resolvers. Split scientific handlers from engine lifecycle;
do not invent a second orchestration framework or relocate modules merely to match
a fashionable directory tree. Upstream prompts keep their attribution and hashes.
Preserve all scientific loops, attempts and stopping semantics. External scientific
quality, model substitutions and integration availability retain their existing
fidelity limitations until measured.
