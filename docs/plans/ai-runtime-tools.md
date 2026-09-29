# Shared runtime boundaries and executable assets

Base: `9cd457d` (AI architecture audit and refactor acceptance plan).

## Requirement and scope

The AI-native platform audit identifies private helpers imported from the experiment
executor and complete executable programs hidden inside strings. Extract the shared
filesystem/process primitives into `runtime_support` with explicit supported names;
keep experiment scheduling, validation, evidence receipts and protected evaluation in
the executor. Extract the Slurm worker, synthetic benchmark and public evaluation
programs into packaged Python source assets. The programs remain copied into private
workspaces and launched under the existing execution policy.

This branch owns `runtime_support`, `execution.py`, `evaluation.py`, `demo.py` and
focused tests. Other callers retain temporary compatibility imports until the
coordinator updates them during integration. Store accounting is outside this scope.

## Acceptance and validation

- Preserve race-resistant descriptor traversal, path validation, atomic writes,
  bounded logs, process-group cleanup, scheduler receipts and immutable evaluator
  handling. Never turn unsuccessful commands or measurements into acceptance.
- Public evaluation and synthetic demo algorithms and fixed protocols stay unchanged.
- Executable assets are ordinary inspectable Python files included in installed wheels.
- Test malicious paths/symlinks, process timeout/truncation, Slurm runner execution,
  deterministic demo output and protected scorer rejection of invalid predictions.
- Run focused execution/evaluation/coding/integrity tests, lint/type checks, public
  scan and offline demo; independent review belongs to the coordinator before merge.

## Evidence

Primitive extraction implemented and independently reviewed by the coordinator
against `9cd457d`; no actionable findings. Focused runtime/execution/evaluation/
coding/inspection suite: 86 passed. Ruff lint and formatting pass. Strict mypy
reports only the inherited `tui.py:106` async override mismatch, owned by the
coordinator. An initial compatibility export typing failure was resolved by
explicit `execution.__all__` declarations; no scientific attempts occurred.

Executable assets extracted under `assets/programs` with an allowlisted packaged
resource loader. Runtime/program/execution/evaluation/coding/inspection/fidelity
suite: 110 passed. Strict typing passes on all 11 new runtime and program modules;
full typing retains only the inherited TUI override mismatch. Ruff and public-file
scan pass. An offline wheel build initially failed because the pinned Hatchling
backend was absent from the cache; a normal build fetched the existing pinned
backend and produced both sdist and wheel. All five source assets loaded from the
wheel with the checkout absent from Python's import path, and its standalone demo
matched the pre-refactor measurement exactly. No lockfile/dependency changes.

The coordinator independently reviewed the asset diff and actual worker/training/model
sources; no actionable findings. See the review record. No paid calls or live scientific claims.
