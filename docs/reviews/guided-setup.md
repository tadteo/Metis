# Guided setup and settings independent review

Base: 0425e2a. Reviewer: independent setup_review agent in a separate managed checkout,
reviewing the feature diff plus new files against the persisted task plan.

Finding P2: Advanced JSON recursively merged the edited document into saved defaults,
so clearing role_providers (and other advanced maps) silently restored removed entries.
Reproduced by the reviewer using the real browser code. Resolution: authenticated,
side-effect-free schema normalization treats JSON as a replacement; populated forms
preserve intentionally empty maps. Added HTTP normalization/auth/no-save tests, a
browser override-removal regression and a stale-response regression.

Initial independent checks: 25 settings/TUI tests and 12 browser tests passed. Reviewer
did not independently exercise a graphical browser or live services. Primary agent
visually inspected first launch, Settings, dataset navigation, missing-prerequisite
messages, and saving/reopening incomplete settings without creating a run.

Final independent follow-up and release evidence are recorded below after completion.

Independent follow-up: P2 resolved; no new actionable findings. Reviewer independently
passed all 14 browser tests and 26 HTTP tests, including removal, authentication and
normalization without persistence. Graphical/live-service limitations remain unchanged.

Release evidence: full pytest before the narrow review correction: 741 passed, 3 opt-in
checks skipped (206.53 s). After correction, affected settings/HTTP suites: 33 passed,
including both 110×40 and 80×24 terminal settings flows. Node: 14 passed. Ruff lint,
formatting, mypy, specification validation, public-file scan and scanner self-test pass.
Installed wheel before the correction: 1 package test passed. Synthetic end-to-end demo
completed with 34 experiment records, retaining the previous best after rejected meta
refinement. No paid models, real cluster jobs or live research-quality claims were made.

Final packaged artifact after the review correction and fidelity regeneration: wheel
built successfully; installed-wheel check passed (1 test). Fidelity matrix checks passed
(17 tests). Integration inventory found concurrent remote-interface work in its own
checkouts; those uncommitted files were preserved and not included in this feature.
The integration checkout remained clean at the recorded base before merge.
