# Runtime foundation integration

Base: d7b006b on codex/runtime-foundation, using the existing isolated writer-supervision
worktree after its clean, reviewed supervision task. The source snapshot is the concurrent
implementation frozen in /private/tmp/scientisttwo-concurrent-final.json; this is integration
of real existing work, not a claim that it was authored after the import.

Scope: coding command-created source export; Laya's real typed HTTP advisory transport and
accounting; local readiness checks for writer/credentials/runtime. Own coding.py, laya.py,
setup.py, their focused tests, docs/coding-harness.md and .env.example. Do not change engine,
agents or writer integration owned by other branches. Preserve all failure evidence.

Plan:
1. Verify frozen-file digests, compare against the branch, then apply only scoped changes.
2. Validate new-source export without retaining pilot predictions/checkpoints. Preserve
   explicitly edited and renamed source, require a successful test for exported code, and
   reject unsafe/protected exports.
3. Verify Laya's public typed contract against upstream source; reject malformed responses,
   keep failed-call accounting, and retain the independent reasoning path as authoritative.
4. Validate readiness without model API calls; probes must establish a usable runtime.
5. Run focused tests, lint/type checks, request root's independent review, record findings,
   then commit small Conventional Commits. Root merges after review.

Acceptance evidence: executed coding test/repair/export regressions; mocked actual Laya HTTP
request/response contract, usage and failure tests; preflight credential/tool/runtime tests.
Live service quality/cost and autonomous scientific capability remain separate measurements.

Implementation and review complete. Imported only scoped hash-verified snapshot files;
strengthened generated-source registration, typed external response validation and persisted
privacy behavior after reproducing failures. Independent workflow_review found no blockers
and independently passed 69 tests. Details and remaining measurement limits are recorded in
../reviews/runtime-foundation.md. Root integrates alongside the separately reviewed dataset
SHA-256 executor prerequisite 4d3fb3d; no executor/agent/engine/writer source was replaced.
