# Writer supervision review evidence

Implementation: `codex/writer-supervision`, layered on the parent's official-writer accounting foundation. Independent root review approved the core implementation after inspecting the focused delta and independently running its original 19-test suite (19 passed). The review confirmed container/group cleanup and conservative torn-tail recovery. A subsequent one-line guard also rejects an empty process listing as uncertain; its additional regression is included in the final 20-test suite and was disclosed to the reviewer.

## Reproduced defects

- An exited Docker client caused zero container cleanup/reconciliation calls, even though its named worker could remain active.
- A real local worker spawned a child that ignored SIGTERM. The leader exited with -15, while the descendant remained active after the old stop helper returned. The test process family was explicitly cleaned up.
- A complete usage row followed by a torn trailing JSON record raised JSONDecodeError on every accounting resume and stranded the reservation.

## Implemented safeguards

The container state and complete local process group are checked independently of the leader's exit flag. Uncertainty retains reservations. Cleanup escalates to SIGKILL for remaining local descendants. Defunct zombies are distinguished from active workers because they cannot send API requests or write journals.

Journal repair covers both usage.jsonl and requests.jsonl only after verified worker termination. Interrupted trailing bytes are preserved by content hash, preceding durable reservations remain conservative evidence, and complete JSON records missing a final newline retain their contents. Interior corruption and invalid newline-terminated records require explicit reconciliation.

## Validation

`tests/test_writer_supervision.py` and `tests/test_writer_accounting.py`: 20 passed. Tests include real local descendants, Docker state mocks, cumulative accounting after interrupted reservation/completion tails, repeated recovery, live-worker refusal, and preserved corrupt bytes. Ruff passes on the changed source/tests; mypy passes on paper_orchestra.py and writer_accounting.py. No paid models or remote services were used.

## Remaining boundary

Local mode retains its documented trusted-host assumption. A process that deliberately detaches into another session is outside the owned process group; Docker remains the isolated default. These operational tests do not establish scientific writing quality.

## Combined foundation review and final validation

Final integration base: `357d4a3`, including Store accounting support from `5a12839`. The combined patch preserves the official writer, plotting service, atomic file writer, subordinate call limit, and explicit legacy settlement utility. The normal run path uses WriterAccounting and refuses unsupported legacy records before attempting automatic repair. Subordinate events precede settlement so overruns retain the attempt denominator.

Root independently reviewed the final lifecycle delta, WriterAccounting, and completed-fast-path regressions and reported no blockers. Final validation: 70 tests passed across writer supervision, writer accounting, writing, Store, and architecture suites. Ruff, mypy for the affected source, and git diff --check pass. This includes no-relaunch/no-double-bill completion, retained reservations for active children, event-before-overrun settlement, legacy fail-closed behavior, and symlink journal rejection.
