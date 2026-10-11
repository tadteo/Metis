# Execution runtimes integration review

Reviewed `main...codex/execution-runtimes` at `fc95b40` against base `7c34a8d`.
Two independent agents inspected standards/security and originating specification fidelity.

## Findings and resolutions

- P2: bubblewrap received protected ancestor directories, making sibling files read-only.
  Reproduced with a nested evaluator argv regression before the fix (one failed, one passed).
  Linux now binds only individual protected files; Seatbelt retains literal ancestor denies.
  The standards reviewer independently accepted the fix with no new issues.
- Minor: reproducibility guide incorrectly excluded dataset mounts for all Slurm jobs.
  Qualified the statement to Slurm without a container.

No other substantiated security blocker or specification mismatch was found.
Real Podman, Apptainer, bubblewrap and cluster validation remains open.
macOS sandbox leftovers and same-user process environment visibility remain documented limits.

## Public artifact checks

Scanned all 70 outgoing commits and 834 unique file blobs before the integration fix,
including commit messages: no scanner findings. Independently OCR-reviewed all 57 unique
screenshot blobs across that history and visually inspected the API-key screenshot:
no private paths, personal identifiers or credential values found; key field empty.
OCR plus targeted inspection is a heuristic check, not exhaustive visual certification.
No private runtime files or local machine paths are included in this review record.

## Validation

Formatting, lint, types (90 modules), AI specification validation, 109 browser tests,
public-file scan, scanner self-test and synthetic demo passed.
Live focused macOS/Docker evaluator isolation checks: five passed, including the
Docker leftover-process attack using the existing default Python image.
An initial restricted run failed three Seatbelt tests because the outer execution sandbox
refused sandbox_apply; the authorized live run above passed them.
Installed wheel release check: one passed.
The initial full suite under the outer sandbox ended with 16 failed, 1207 passed,
5 skipped and 77 errors (366.26 seconds); denied sandbox application, socket binds
and other host operations make that run unsuitable as the release gate.
The full authorized suite is recorded below after completion.

Final authorized full suite: **1301 passed, 5 skipped** in 397.92 seconds.
Independent review accepted the fix; live Linux/cluster validation remains open.
