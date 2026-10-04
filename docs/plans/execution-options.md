# Execution choices and ScientistTwo setup

Base: `236da46`. Request: selectable execution in GUI/TUI/CLI, understandable
backend differences, and an audit of parallel experiments and paper code isolation
against ScientistTwo. Work in isolated `codex/execution-options`.

Expose Execution in the normal browser inquiry journey; preserve existing TUI/CLI
selectors and improve their explanations. Expose existing per-job CPU/memory/GPU
settings without implying local enforcement or aggregate resource scheduling.
Record current serial within-run execution, private snapshots and workspace
isolation, separate writer configuration, SSH location, and published-source gaps.
Do not infer upstream concurrency or implement an unrequested scheduler from guesswork.
Scope clarification received no reply during implementation; proceeded with selectors and the explicit concurrency assessment. Within-run scheduling remains unchanged.

Acceptance: backend and resources survive navigation, configuration round trips and
save/new-run flow; local opt-in remains explicit; no experiment starts from setup.
Test browser selection/navigation, TUI at 80x24 and 120x40, CLI persistence, and
validation. Inspect light/dark desktop/narrow browser rendering and keyboard flow.
Run repository checks; independent review, commit, fidelity evidence and merge.

Attempts: initial branch creation was denied by the filesystem sandbox; succeeded
through the approved Git escalation. No source was changed by that failed command.


## Evidence and review

Implemented normal browser Project → Execution → Review navigation, contextual
Docker/local/Slurm explanations and existing CPU/memory/GPU controls. Shared FIELDS
exposes those controls/help to TUI and CLI. Local permission remains explicit;
local resource allocation is not presented as enforced. Documented current source
copies, serial within-run scheduling, separate writer configuration and SSH location.
The primary-source audit does not invent unreleased ScientistTwo scheduling details.

Initial browser suite: 92 passed. Focused settings/execution/interface suite: 72
passed. All browser suites: 99 passed. Ruff lint/format, mypy (84 source modules),
spec validation, public scanner and scanner self-test passed. Installed wheel:
1 passed in 41.65 seconds. Synthetic demo completed with the previous best retained
when meta refinement was not superior; no scientific-quality claim follows.
Full suite: 1,034 passed, 3 skipped in 356.65 seconds.

Visual/interaction evidence: browser 1280x900 and 390x844, light and dark themes;
Docker/Slurm/local explanations and selected states, resource persistence, local
unchecked opt-in, keyboard Next/Back/Tab with visible focus and scroll-to-input.
Inspected incomplete configuration review: checks allow creating an idle agent-entry
run while execution prerequisites remain deferred; no live run was created or
started. Runtime permission enforcement is unchanged. Temporary state only; no
provider call, Slurm submission or Docker experiment. Stored public screenshots:
`docs/evidence/execution-desktop-light.png` and `execution-narrow-light.png`.
TUI rendered at 80x24 and 120x40 in both themes; inspected selection via
Enter/Down/Enter and Tab scrolling to CPU controls. Automated persistence checks
save resources and verify fresh CLI/TUI configuration without creating research.
Raw terminal SVGs remain in disposable validation storage. Temporary servers/tabs
were closed and viewport reset.

Independent reviewer `/root/execution_review` approved against `236da46`, no
blocking findings. It independently ran 92 browser tests and diff whitespace
checks, traced setup callers and executor resource arguments, and verified the
ScientistTwo source boundary. See `docs/reviews/execution-options.md`.

Attempts preserved: initial TUI tests failed twice because the test clicked before
the Settings transition finished; added a Pilot pause and reran successfully.
A browser label lookup matched multiple elements; switched to the observed unique
textarea id. Read-only searches initially named a nonexistent controller file and
unmatched worker glob; corrected to `ResearchWorkers` in tui.py. The screenshot
server received an irrelevant favicon 404. No failed scientific attempts occurred.

Pre-integration inventory: main remained clean at `236da46`; another task's
`codex/stage-reports` checkout has overlapping UI edits plus new reporting files.
Those changes remain untouched in their isolated branch. No other checkout was
modified or archived by this task.

Feature commit: `bd3e74a`. Fidelity mapping records this actual reviewed commit and
the current serial scheduling limitation.

Integrated without conflicts as `545b23b`. Final rebuilt installed-wheel check
passed (1 test, 43.52 seconds). Independent reviewer reapproved the completed
evidence and fidelity changes with no additional findings. Main was clean before
this final evidence entry; unrelated stage-report work remains untouched.
