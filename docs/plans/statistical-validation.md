# Planned statistical method validation integration

Status: implemented, tested, independently reviewed and approved for commit. Base: reviewed literature branch `c9021df`.

## Requirement and compatibility boundary

Integrate the useful concurrent paired sign-flip plan, exact arithmetic and significance-text checks. Preserve the independently reviewed generic protected-evaluator receipt contract (`a02d767`), literal numerical spans/units, exact input fingerprints, and independent statistical reproduction (`865edd7`). This is integration and adaptation of existing concurrent work, not a claim of newly authored statistical validation history.

## Plan

1. Reuse the isolated worktree on `codex/statistical-validation`. Capture the inherited main source/tests/docs and record hashes before edits.
2. Extract a focused `planned_statistics` module: typed paired sign-flip plan, pre-execution registration, matched-pair/protocol/source/dataset/unit validation, exact sign enumeration and Bonferroni correction, explicit significance conclusion checks. Keep assumptions and completeness of the declared family explicitly unverified.
3. Extend the existing executor/evidence contract rather than add a second loose-file attestation path. A present `statistical_plan.json` is captured before generated execution when outputs are registered. Generic output schema and fingerprint checks remain unchanged. Validated method evidence is an additional receipt field. Generic executed values remain distinguishable from method-validated significance.
4. Carry the immutable protocol, source, dataset and units in host input descriptors. Preserve original registered plans during reproduction. Keep literal values, numeric_span and units authoritative; require a validated supported method for significance/nonsignificance assertions.
5. Adapt inherited adverse cases into actual protected-evaluator integration regressions, including missing/late plans, invented arithmetic, multiplicity, wrong conclusion wording, altered inputs and preserved generic statistical behavior. Run affected suites/static checks and obtain independent root review before commit.

Scope: planned statistical module, narrow integrity/executor/engine/prompt integration, focused tests and docs. Do not edit main or overwrite its broader pending implementation. Statistical assumptions are scientific judgments; this task certifies registration timing and executed arithmetic only.

## Inherited snapshot

Pending main HEAD at capture: `0bdbd07`. These uncommitted files were authored concurrently; exact snapshots are retained in the local temporary audit directory `/private/tmp/statistical-validation-inherited` while integration is in progress.

- `src/autoresearch/integrity.py`: `8595b3a81ea132fdb569c116091375b3c38b4c51f2b22edcb785bbc4afb0a927`
- `src/autoresearch/engine.py`: `f5d9753b85be182fac5f452a3c041eb3ab7592b64c54306e9450a733390d895b`
- `src/autoresearch/prompts.py`: `e291c1d1a9030d76608f4bf1c072fbd5451f2fd427c446f01015cbd9ece960ae`
- `tests/test_integrity.py`: `5b8eb57192dd1fe85e5ceada8e20aeb8d6229b06c2c567cf06b022130b02c3da`
- `docs/statistical-analysis.md`: `1108deeb86bf480a715c3c0421c68001efd18d3a002db39121e14cc9f212cdc1`

## Integration decisions

The final frozen concurrent snapshot (`dd5ea451520072415e742484fccbb401f00014a6`, manifest `/private/tmp/scientisttwo-concurrent-final.json`) has identical hashes for the inherited integrity implementation, tests and statistical guide captured above. Nothing in those latest statistical changes was silently dropped.

The inherited plan schema, exact sign enumeration/Bonferroni method, matched-seed/protocol/source/dataset requirements, finite-number guards and explicit conclusion/number-label checks are adapted into `planned_statistics.py`. The existing generic artifact schema is retained: two separate declared outputs can report p-value and mean effect. Its stronger registered-input fingerprints, protected-evaluator capture, literal-value/unit binding and reproduction semantics remain in force. No old fixed-filename loose-file attestation is accepted. Generic methods remain valid executed-value evidence with a method-unverified receipt, but cannot certify significance. Unknown scientific assumptions are explicit receipt fields.

The host registration is captured before generated execution and made available to the protected evaluator as `AUTORESEARCH_STATISTICAL_PLAN`. It is not claimed to predate observation of existing results. The engine passes original registration when reproducing an analysis. Dataset consistency uses recorded provenance without claiming that this validator performs the separate file-manifest verification being integrated by another reviewed task.

Compatibility checks initially exposed optional-plan detection incorrectly treating a missing file as an error; this was corrected without weakening symlink/path rejection. The retained Decimal comparison import was restored after integration tests caught its removal. Subsequent combined claim/planned-analysis/reproduction suite passed all 71 tests before the last additional regression cases. Final validation results and independent review follow below.

## Validation

- Combined planned-statistics, existing claim integrity, analysis reproduction, experiment history, fidelity, engine and executor suites: **169 passed** in 43.69 seconds.
- Focused Ruff checks and mypy on planned statistics, integrity, executor and engine: passed.
- `git diff --check`: passed.

The 36 new test cases adapt the inherited scientific-method checks to actual protected evaluator processes and the stronger generic receipt path, including full input fingerprints. Additional cases preserve generic unvalidated executed values, forbid their use for significance, verify independent reproduction rejects changed plan registration, and retain finite numeric-span handling. Root independent review was completed before commit `7c1875c`; its findings and independent 78-test run are recorded below.

Final numeric edge-case check rejects nonzero literals that underflow to zero (±1e-324). After this narrow addition, planned-statistics and existing claim-integrity suites passed **73 tests** in 6.89 seconds; focused Ruff checks passed.

## Independent review

Root reviewed the new method module, executor registration/provenance changes, claim/reproduction integration, tests and documentation. No blocking findings. Root independently ran planned statistics, analysis reproduction and claim integrity: **78 passed** in 8.82 seconds, then approved this focused integration commit. See `docs/reviews/statistical-validation.md`.
