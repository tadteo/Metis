# Metis identity review and validation

Base: `3502385`. Branch: `codex/autoresearch-identity`.
Requirement: [Metis naming plan](../plans/metis-identity.md).

## Independent review

Independent agent `metis_review` reviewed the implementation and untracked workflow
against the recorded base. Approved with no actionable findings. It verified:

- Workflow changes are limited to identity/version; all scientific gates persist.
- All 45 consumers of the local common prompt receive version bumps. The typed
  `laya_triage` renderer bypasses that prompt and correctly retains its version.
- Both command names resolve to the same implementation; Python import namespace,
  environment variables and state paths retain compatibility.
- Upstream attribution, historical records and frozen-run upgrade constraints remain.
- Canonical and packaged matrices agree; diff whitespace checks pass.

The review's initial audit asserted that every role version must change. It failed
on `laya_triage`; inspecting the typed renderer corrected that overbroad audit
assumption. This was a review-script error, not a product defect.

## Commands and evidence

- Initial `uv lock --offline` failed because required metadata was absent from the
  cache. Online `uv lock` and frozen install succeeded. The only lock change is the
  renamed editable root package; dependency versions and hashes are unchanged.
- Focused CLI/catalog/workflow/provenance/matrix/settings suite: 95 passed.
- Formatting first reported `setup_cli.py`; formatter applied its line wrapping.
  Subsequent full format check and lint passed; mypy passed for 62 source files.
- `metis validate-specs`: 46 agents, 28 stages, valid.
- Browser suite: 14 passed. Public-file scanner and scanner self-test passed.
- Wheel `metis_research-0.1.0-py3-none-any.whl` built successfully. Installed-wheel
  check outside checkout: 1 passed in 40.07s, including both CLI entry points,
  packaged Metis workflow and synthetic end-to-end execution.
- Separate `metis demo` in temporary private state completed with 34 experiment
  records and outcome `previous_best_retained_meta_refinement_not_superior`.
- During full pytest, formatting ran after a run had archived its source identity.
  `test_complete_real_experiment_workflow_and_resume` correctly blocked with
  `AI behavior changed since this run was created`. Its fixed-source rerun passed
  in 42.22s. The failed attempt is retained here; no guard was relaxed.
- First full suite: 742 passed, 3 skipped, and the one provenance-guard failure
  described above (184.54s). Final frozen-source full suite: **743 passed, 3 skipped in 236.15s**.
  Skips are opt-in installed-wheel/upstream checks; the wheel ran separately as above.

No paid-model, live Docker/TeX or scientific-performance evaluation is claimed.

## External naming

The checkout initially had no remote. Read-only inspection established that
`tadteo/auto-improve-research` is a different project; it was not modified. The user
then explicitly requested a new GitHub repository. Created private
[Metis](https://github.com/tadteo/Metis) and configured it as origin. Push is pending
local integration checks.

Codex reports the saved project as AutoResearch. No available tool renames a
project, and the computer-use tool explicitly refused access to the Codex app.
The label therefore requires a manual user rename. The checkout path and existing
chat/worktree associations remain intact; no unsupported settings edits were made.

Before integration, all 16 checkouts were inventoried. Main was clean; ongoing
remote-transport and remote-web edits were left in their own worktrees. No
concurrent branch was absorbed into this naming change.

Implementation commit: `29da4b9`. The canonical evidence matrix records this
identity change under runtime_interface and ai_behavior_contracts.
