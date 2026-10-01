# Bounded evidence context

Base: `e6bee9f`. Status: implementation, independent review and release checks complete; ready for integration.

Implement the first focused slice of the reviewed ScientistTwo-informed design:
bounded display of oversized bibliographic metadata, exact evidence payload reuse
within a request, and projection before coding/intake history selection. Retain raw
records, hashes, all attempts, scientific passages, budget semantics and stage gates.
Handle oversized history observations with explicit indexed omissions and existing
history/read access; do not invent tools for panels that lack them.

Instructions remain external Markdown in the packaged specification bundle; any
shared presentation guidance and affected agent versions must be updated together.
Explain existing partial-result views and private storage rather than duplicating
the newly merged process/trace UI. Provide an inspectable local partial-run view if
possible without execution or migration of the original diagnostic.

Validation: adverse synthetic request/checkpoint regressions before implementation;
real private trace replay offline; relevant then full tests, static/spec checks,
browser suites, wheel smoke, public scanner and demo. Independent review then
commit/fidelity evidence/merge. No new live model calls or runtime mutation of the
original diagnostic. Focused search and relevance policy remain a later slice.

## Implemented and observed

Added a shared schema-aware evidence projection, exact-copy request references,
projection-first history selection and paged access to privacy-redacted oversized
steps, with separate original/view hashes. Titles/venues have explicit display bounds; scientific passages and arbitrary
scientific fields are preserved. External common/history/intake/coding prompts and
catalog versions describe the new presentation without inventing panel tools.

The initial public regression failed at 185,381 serialized characters for one record.
After implementation 117 focused tests pass. Offline replay of the private original
limitations request reduces its prompt from 654,640 to 46,871 bytes, with a USD
1.048452 reservation under the current system prompt versus the original USD 8.334900.
The eight-step intake history fits in 59,323 characters; the checkpoint hash is
unchanged. This is no-call software evidence, not a live relevance/quality result.

The existing process graph, Agent traces, artifacts and AI system views already
expose partial work. The diagnostic report was opened for inspection. The private
run contains an intake brief and source evidence; measured baseline controls are
separate from the incomplete research run. Data remains in private SQLite plus
run-owned files; no runtime data is copied into Git.

## Review and validation chronology

Independent reviewer `journey_review` found that paging before structured privacy
redaction could expose credentials, and deduplication before redaction could leave
unresolvable pointers. Both were reproduced and corrected. A second pass found
secrets crossing a title/venue display boundary; runner/history regressions failed
before the fix and pass with redaction before projection. Review prompt variables
follow the same ordering. Original checkpoints and raw review evidence are preserved.
The review regression initially captured the final panel's deliberately raw input
before AgentRunner redaction; it now asserts the actual review subcall boundary.
The independent reviewer verified the corrected regression and approved the runtime.

An intermediate full run passed 1,005 tests with three environment-dependent skips;
it preceded the final privacy-boundary additions. Two development runs were
interrupted while correcting review findings/fixtures. Final affected tests: 61
passed. Static types (84 source files), lint, formatting, specification validation
(48 agents/29 stages), 98 browser tests, rebuilt wheel smoke and public scanner
including its self-test pass. Synthetic demo completed. The final full run passed 1,008 tests with three skips (wheel checked separately;
two optional official-writer checkout tests were unavailable); no live model calls or paid compute were used.

Pre-integration worktree inventory found concurrent changes in `codex/ponytail-coding`
(agent catalog, its plan, evaluation assets and efficiency prompt). Those files stay
in that checkout and are not included here. Other existing checkouts were clean.
