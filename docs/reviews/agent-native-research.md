# Independent review: agent-led research plan

Base: `8dbc4ac`. Scope: documentation-only proposal and primary-source audit.
No implementation or paid scientific evaluation was requested or performed.

Source audit author: `/root/scientisttwo_input_audit`, isolated branch
`codex/agent-native-source-audit`. The primary agent independently checked its
claims against the cited paper sections, requested explicit Google Search attribution
for the two novelty references and approved it. Original commit `2e04e28` was
cherry-picked as `01128f8` on the planning branch; authorship is preserved.

Plan reviewer: `/root/review_agent_native_plan`, independent read-only review of
repository source, plan, user request and companion audit. Findings:

1. P2: Intake needed explicit persisted completion, needs-input/access, interruption,
   budget exhaustion and unresolved outcomes. Generic intervention feedback alone
   could not specify how clarification revises the brief and invalidates cached work.
   Resolved with the outcome table, attributed input/brief versions, normal lease and
   state-version checks, stale-result invalidation and explicit Resume semantics.
2. P2: The draft risked introducing unnecessary comparison-policy changes. Current
   default scientific_critic already requires independent critic acceptance plus a
   necessary measured gain; primary-metric gating belongs to optional pareto policy.
   Resolved by preserving default semantics and imported pareto compatibility, moving
   discovered metric/reference inputs into artifacts, and separating any later
   adjudication-policy change from the autonomy refactor.

Final re-review approved the planning-only merge with no remaining blocking findings.
The reviewer found the scientific loops, budget enforceability distinction, evidence
integrity, compatibility and unknown upstream details appropriately preserved. Approval
covers planning consistency, not implementation or scientific performance parity.

Validation: local Markdown links and public-file scanner pass; staged diff whitespace
checks pass. No executable behavior changed, so runtime regression suites and new UI
screenshots were not run for this task. An initial scanner command assumed a worktree
`.venv` that did not exist; rerunning with the existing integration interpreter passed.
