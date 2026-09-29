# Cached agent provenance review

Base: `f63e123b340e1bec224409bbaa0785404e3583ce`.
Independent reviewer: root integration agent; implementation author: runtime/statistics agent.

The originating Standards finding was a demo cache hit labeled as the configured live model, with similar ambiguity for injected providers, command adapters and repaired requests. Six deterministic regressions reproduced those failures after correcting an unrelated fixture-ID mistake.

The reviewer independently inspected the typed cache envelope, producing-call versus logical-lookup fields, legacy fallback and new tests. It approved the implementation and TUI recent-call visibility: actual model/provider/call/request identities are preserved, legacy unavailable identities remain unknown, and output validation, cache fingerprints and call accounting remain unchanged. No remaining actionable finding was reported before commit.

Author validation: 74 expanded agent/catalog/specification/behavior tests passed; the six cache cases plus changed TUI inspectability fixture passed (7 tests). Both affected source modules passed mypy; scoped Ruff/format, diff check and public-artifact scan passed. The first fixture invocation failed on its run-ID format, then the six intended behavior failures were observed before the repair. A broad TUI launch lacked a retained session identifier; its result is not claimed. No paid provider was called.
