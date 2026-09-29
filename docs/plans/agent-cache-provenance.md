# Preserve the provenance of cached agent results

Base: `f63e123b340e1bec224409bbaa0785404e3583ce`.
Branch: `codex/cache-provenance`, isolated reusable runtime worktree.

## Finding and intended boundary

Final independent Standards review reproduced a demo cache hit labeled `grok-4.7` / `xai`, although the successful response was `offline-scripted-fixture` / `demo`. AgentRunner stored only the validated scientific output and reconstructed cache-event model and request metadata from configuration. Injected adapters and repaired requests had the same provenance ambiguity.

Keep actual successful response identity, call ID and request/provenance in a typed, versioned cache envelope. Keep logical lookup metadata separate. Old bare AgentOutput cache entries remain usable after validation, with unavailable response identity explicitly unknown and configured names clearly labeled. Do not change scientific output, provider selection, repair/escalation rules, costs or cache lookup keys. No paid calls.

## Acceptance and evidence

- Add deterministic regressions for demo, injected and command-adapter identities, repaired requests, frontier reuse and legacy cached results.
- Run them before implementation to reproduce the gap, then targeted agents/behavior/catalog and cache suites, Ruff/mypy and the public-artifact scanner.
- Request independent root review before a coherent commit; record actual findings and results here and under docs/reviews.

## Implementation and verification

- Initial regression invocation caught an invalid synthetic run ID in the fixture. Corrected it to the required hexadecimal format; all six behavioral cases then failed on the actual provenance defects before implementation.
- Added a typed `agent_response.v1` cache envelope. Cache lookup keys, scientific validation, provider repair/frontier control flow and cost settlement remain unchanged. Cache hits revalidate the output and report its stored producing-call receipt; legacy entries report unknown identity.
- All six focused regressions pass. Agents, behavior, catalog and specification selection: **74 passed in 5.26 seconds**. Scoped Ruff/format, one-module mypy, diff check and public-artifact scanner passed. The first Ruff check could not write its worktree cache under the sandbox; `--no-cache` passed.
- TUI exposes the new receipt/lookup fields in recent calls; the existing inspectability fixture verifies explicit legacy-unknown rendering. Exact six-cache plus changed TUI fixture selection: **7 passed in 1.47 seconds**. A broader UI invocation's session identifier was not retained, so no completed result is claimed for that invocation. Both affected source modules passed mypy; Ruff, formatting, diff and public-artifact checks passed.
- Independent root review approved the source, all six cache regressions and TUI field handling before commit. The reviewer confirmed actual producing-call identity through repair/frontier reuse, honest unknown legacy identity, unchanged scientific output/call accounting and unchanged cache fingerprints.
