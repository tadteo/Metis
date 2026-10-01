# Ponytail coding policy and pilot review

Base: e6bee9f. Independent reviewer: `/root/quality_review` (read-only).
Final decision: approved, no remaining actionable findings. The reviewer independently
ran the final six benchmark regression tests successfully.

Findings and resolutions:

1. Outage stopping used zero output tokens, but unknown provider outcomes receive
   nonzero conservative estimates. Stop on ProviderError and record per-call flags.
2. Exit zero could pass without tests executing. Require the explicit seven-group
   completion receipt and evaluate only the specified exported summary.py.
3. Reusable runner inherited unrelated project metadata/mounts. Construct a fresh
   synthetic ProjectConfig, clear references/data mounts/resource hosts and disable
   cache/frontier. The actual initial request had been inspected offline and already
   contained no private research or credential values.
4. A frozen fixture copy existed but evaluation read the live fixture afterward.
   Use the copied fixture exclusively for task/source/hashes/acceptance. A regression
   mutates a temporary live fixture during execution and verifies frozen checks run.

Scientific review: the optional policy preserves baseline/method fidelity, splits,
seeds, ablations, statistics, evidence, security and meaningful checks. Tool permissions,
validators and every other agent remain unchanged. Default agents.json is byte-identical
to base; only explicitly created optional bundles use coding-step version 4.

Evidence review: all 10 live attempted failures and four unattempted planned slots
remain represented. Reported-token price estimates and unknown reservations are
separate. No live acceptance completion, cost savings or quality equivalence is claimed.
The failed adoption gate prevents a default rollout. Single-response results are
separate from coding-loop attempts. Complete private journals are archived, not
published. Existing runs/settings are untouched.

Validation: full offline suite 1001 passed / 3 expected skips before the final opt-in
and scorer refinements; final affected coding/spec/behavior suite 49 passed; final
pilot suite 6 passed (including independent rerun). Browser suite 98 passed; mypy
83 source files; Ruff lint/format and specification validation pass. Final opt-in
wheel installed test passed, and synthetic demo completed with empty error. Public
scanner and scanner self-test pass. The packaged policy and MIT notice are present.
These establish software behavior only.
