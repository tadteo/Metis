# AI-native research platform refactor

Status: implementation integrated on `codex/ai-native-platform`; final system review and release checks in progress. Inherited integration base is recorded separately.

## Requirement and audit

User request (2026-09-29): audit the entire actual repository against ScientistTwo
arXiv:2609.19644v1 and existing fidelity requirements before modifying code; make
agents, prompts, workflow, routing, validation and provenance explicit without
removing scientific stages. See docs/ai-architecture-audit.md for the pre-change audit.

## Sequence and ownership

1. Preserve existing uncommitted integrations in an honest baseline commit on an isolated branch; keep the original checkout untouched during implementation.
2. Add a packaged AI specification layer: external prompts, validated agent definitions, model/tool/context/output policies. Route real calls through it.
3. Replace implicit stage dispatch with named scientific handlers driven by a validated workflow graph. Preserve every measured-evidence gate and failure history.
4. Freeze resolved behavior/provenance per run; make routing and artifacts inspectable in CLI/TUI/web. Prevent held-out feedback contamination.
5. Consolidate shared runtime helpers and embedded executable assets where useful; add semantic contract, provenance, workflow, packaging and UI regressions.
6. Run full repository checks and offline demonstration; request independent Standards and Spec reviews; resolve findings before merging coherent Conventional Commits.

Parallel implementation uses separate worktrees. Catalog owner: AI definitions/prompts/agent runner. Workflow owner: engine dispatch/scientific handlers/workflow graph. Coordinator: run provenance, interfaces, documentation and integration. Shared interfaces are agreed before changes.

## Acceptance and evidence

- Every live agent has role/input/output/tool/model/prompt/validation/escalation declarations; locally authored instructions live in artifacts.
- Coding receives both its scientific role instructions and tool protocol; held-out evaluation cannot feed subsequent optimization.
- All ScientistTwo stages and feedback transitions are inspectable and tested; successful code tests never substitute for measurements.
- New/resumed runs identify and verify immutable prompt/agent/workflow/schema/config provenance; no silent instruction drift.
- Custom agents/prompts/models can use existing handlers without changing core dispatch; new executable tools still require trusted implementation and checks.
- Provider, sandbox, budget, resume, private storage and UI controls remain functional; installed packages include behavior assets.
- Ruff, mypy, pytest, Node UI suite, public-content scan and offline demo pass. Record original failures separately. Live scientific capability/model quality is explicitly outside offline evidence.
- Independent review, meaningful commits and final integration evidence are persisted.

## Completed implementation boundaries

- Packaged catalog and model/tool policies execute 46 declared roles, including typed advisory
  and versioned evaluation task templates, with external scientific instructions,
  structured-output checks and per-call provenance.
- Twenty-eight workflow stages dispatch through trusted scientific handlers; graph
  edges, evidence gates and declared agent dependencies are validated.
- Runs pin resolved behavior/source identities and refuse silent drift. Legacy
  adoption reconciles specialist checkpoints and outstanding calls before pinning.
- Shared runtime primitives and packaged executable programs preserve the existing
  experiment/evaluator behavior. Generic aggregate accounting owns all model costs.
- CLI/TUI/web expose archived agent instructions, routing and graph provenance.
  Installed-package checks and reconciliation of later concurrent scientific repairs
  are in final integration.

See `docs/reviews/ai-native-platform.md` for actual failed and successful checks,
independent findings, corrections and final integration evidence. Concurrent repairs
completed on main at `87bf703`; see `ai-fidelity-reconciliation.md` for explicit
scientific ownership, compatibility decisions and integration acceptance.
