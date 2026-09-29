"""Real descendant cleanup and conservative recovery of interrupted worker journals."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import RunState
from autoresearch.paper_orchestra import (
    PaperOrchestraError,
    _assert_previous_worker_exited,
    _process_group_running,
    _recover_writer_journals,
    _stop_writer_process,
    _usage_rows,
)
from autoresearch.store import Store
from autoresearch.writer_accounting import WriterAccounting


def receipt(base: Path, backend: str = "local", **fields: Any) -> None:
    (base / "supervisor.json").write_text(
        json.dumps({"backend": backend, "pid": None, "exited": True, **fields})
    )


def test_exited_docker_client_still_removes_and_checks_owned_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(
            returncode=0, stdout="false" if argv[1] == "inspect" else "removed", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("autoresearch.paper_orchestra._process_group_running", lambda _: False)
    process = SimpleNamespace(pid=12345, poll=lambda: 1, wait=lambda **kw: 1)
    _stop_writer_process(process, tmp_path, {"backend": "docker"})
    assert [argv[1] for argv in calls] == ["rm", "inspect"]
    assert all(argv[-1] == "autoresearch-writer-" + tmp_path.name for argv in calls)


def test_exited_supervisor_flag_cannot_hide_a_live_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt(tmp_path, "docker", pid=12345)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="true", stderr="")
    )
    with pytest.raises(PaperOrchestraError, match="container is running"):
        _assert_previous_worker_exited(tmp_path, {"backend": "docker"})


@pytest.mark.parametrize(
    "stdout,returncode,stderr", [("true", 0, ""), ("", 1, "daemon unavailable")]
)
def test_cleanup_requires_confirmed_container_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int, stderr: str
) -> None:
    def run(argv: list[str], **kwargs: Any) -> SimpleNamespace:
        if argv[1] == "rm":
            return SimpleNamespace(returncode=0, stdout="removed", stderr="")
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", run)
    process = SimpleNamespace(pid=12345, poll=lambda: 1, wait=lambda **kw: 1)
    with pytest.raises(PaperOrchestraError):
        _stop_writer_process(process, tmp_path, {"backend": "docker"})


def start_family(tmp_path: Path, leader_exits: bool = False) -> subprocess.Popen[bytes]:
    marker = tmp_path / "child.pid"
    child = f"import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);open({str(marker)!r},'w').write(str(os.getpid()));time.sleep(60)"
    tail = "time.sleep(0.2)" if leader_exits else "time.sleep(60)"
    leader = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);{tail}",
        ],
        start_new_session=True,
    )
    deadline = time.monotonic() + 5
    while not marker.exists() or not marker.read_text():
        if time.monotonic() >= deadline:
            os.killpg(leader.pid, signal.SIGKILL)
            leader.wait()
            raise AssertionError("child did not start")
        time.sleep(0.01)
    return leader


def kill_family(leader: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(leader.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    leader.wait(timeout=5)


@pytest.mark.parametrize("leader_exits", [False, True])
def test_local_cleanup_stops_children_that_ignore_sigterm(
    tmp_path: Path, leader_exits: bool
) -> None:
    leader = start_family(tmp_path, leader_exits)
    try:
        if leader_exits:
            leader.wait(timeout=5)
        receipt(tmp_path, pid=leader.pid, pgid=leader.pid, exited=True)
        with pytest.raises(PaperOrchestraError, match="process group"):
            _assert_previous_worker_exited(tmp_path, {"backend": "local"})
        _stop_writer_process(leader, tmp_path, {"backend": "local"}, grace_seconds=0.05)
        assert not _process_group_running(leader.pid)
        _assert_previous_worker_exited(tmp_path, {"backend": "local"})
    finally:
        kill_family(leader)


def setup_accounting(tmp_path: Path) -> tuple[Store, RunState, Path, WriterAccounting]:
    store = Store(tmp_path / "state")
    state = RunState(id="abcdef123456", title="Writer", objective="Retain paid evidence")
    store.create(state, ResearchConfig())
    base = tmp_path / "job"
    base.mkdir()
    receipt(base)
    accounting = WriterAccounting(base, store, state, "fixture")
    accounting.reserve_remaining(15)
    return store, state, base, accounting


def line(identifier: str, cost: float, status: str = "completed") -> bytes:
    return (
        json.dumps(
            {
                "id": identifier,
                "cost_usd": cost,
                "status": status,
                "estimated": status == "reserved",
            }
        )
        + "\n"
    ).encode()


@pytest.mark.parametrize("torn_completion", [False, True])
def test_torn_usage_tail_preserves_durable_cost_and_resumes_once(
    tmp_path: Path, torn_completion: bool
) -> None:
    store, state, base, accounting = setup_accounting(tmp_path)
    cost = 10 if torn_completion else 8
    prefix = line("paid", cost, "reserved" if torn_completion else "completed")
    tail = b'{"id":"paid","cost_usd":8' if torn_completion else b'{"id":"not-sent","cost_usd":1'
    journal = base / "usage.jsonl"
    journal.write_bytes(prefix + tail)
    _recover_writer_journals(base, {"backend": "local"})
    assert journal.read_bytes() == prefix
    archives = list(base.glob("usage.jsonl-interrupted-tail-*.bin"))
    assert len(archives) == 1 and archives[0].read_bytes() == tail
    accounting.reconcile()
    assert store.usage(state.id)["cost_usd"] == cost
    accounting = WriterAccounting(base, store, state, "fixture")
    accounting.reserve_remaining(15)
    with journal.open("ab") as stream:
        stream.write(line("second", 2))
    accounting.reconcile()
    accounting.reconcile()
    assert store.usage(state.id)["cost_usd"] == cost + 2
    assert store.usage(state.id)["reserved_usd"] == 0
    assert len(_usage_rows(journal)) == 2


def test_requests_tail_keeps_unresolved_request_and_allows_next_record(tmp_path: Path) -> None:
    receipt(tmp_path)
    prefix = (
        json.dumps(
            {"id": "request", "stage": "outline", "request_hash": "hash", "status": "started"}
        ).encode()
        + b"\n"
    )
    journal = tmp_path / "requests.jsonl"
    journal.write_bytes(prefix + b'{"id":"request","status":"completed"')
    _recover_writer_journals(tmp_path, {"backend": "local"})
    assert journal.read_bytes() == prefix
    assert json.loads(journal.read_bytes())["status"] == "started"
    assert len(list(tmp_path.glob("requests.jsonl-interrupted-tail-*.bin"))) == 1


@pytest.mark.parametrize("name", ["usage.jsonl", "requests.jsonl"])
def test_complete_record_without_newline_is_preserved_and_terminated(
    tmp_path: Path, name: str
) -> None:
    receipt(tmp_path)
    journal = tmp_path / name
    data = b'{"id":"complete","status":"completed","cost_usd":8}'
    journal.write_bytes(data)
    _recover_writer_journals(tmp_path, {"backend": "local"})
    _recover_writer_journals(tmp_path, {"backend": "local"})
    with journal.open("ab") as stream:
        stream.write(b'{"id":"next","cost_usd":1}\n')
    assert len([json.loads(row) for row in journal.read_bytes().splitlines()]) == 2
    assert list(tmp_path.glob(name + "-interrupted-tail-*.bin"))[0].read_bytes() == data


@pytest.mark.parametrize("data", [b'{bad}\n{"id":"valid"}\n', b"{bad}\n"])
def test_interior_or_terminated_corruption_is_not_silently_repaired(
    tmp_path: Path, data: bytes
) -> None:
    receipt(tmp_path)
    path = tmp_path / "usage.jsonl"
    path.write_bytes(data)
    with pytest.raises(PaperOrchestraError, match="Corrupt"):
        _recover_writer_journals(tmp_path, {"backend": "local"})
    assert path.read_bytes() == data
    assert not list(tmp_path.glob("*-interrupted-tail-*"))


def test_live_worker_prevents_journal_repair_and_preserves_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, state, base, _ = setup_accounting(tmp_path)
    receipt(base, "docker", pid=12345, exited=True)
    journal = base / "usage.jsonl"
    data = line("paid", 8) + b'{"id":"inflight"'
    journal.write_bytes(data)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="true", stderr="")
    )
    with pytest.raises(PaperOrchestraError, match="container is running"):
        _recover_writer_journals(base, {"backend": "docker"})
    assert journal.read_bytes() == data
    assert store.usage(state.id)["reserved_usd"] == 15


def test_empty_process_listing_is_uncertain_not_proof_of_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "killpg", lambda *a: None)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="", stderr="")
    )
    with pytest.raises(PaperOrchestraError, match="Cannot inspect"):
        _process_group_running(12345)


def test_legacy_accounting_does_not_trigger_automatic_tail_repair(tmp_path: Path) -> None:
    (tmp_path / "accounting.json").write_text(
        json.dumps({"status": "reserved", "reservation": "legacy-call", "pid": os.getpid()})
    )
    journal = tmp_path / "usage.jsonl"
    original = b'{"id":"possibly-active"'
    journal.write_bytes(original)
    with pytest.raises(PaperOrchestraError, match="Legacy writer accounting"):
        _recover_writer_journals(tmp_path, {"backend": "local"})
    assert journal.read_bytes() == original


def completed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Store, RunState, ResearchConfig, Path]:
    import hashlib

    from autoresearch.paper_orchestra import _resolved_config, digest

    config = ResearchConfig()
    config.paper_orchestra.checkout_dir = str(tmp_path / "upstream")
    config.paper_orchestra.backend = "local"
    config.paper_orchestra.allow_local = True
    config.paper_orchestra.use_plotting = False
    state = RunState(
        id="abcdef123456", title="Writer", objective="Completed path", created_at="2026-01-01"
    )
    store = Store(tmp_path / "state")
    store.create(state, config)
    options = _resolved_config(config)
    payload = state.model_dump(
        mode="json", exclude={"version", "created_at", "updated_at", "status", "error"}
    )
    fingerprint = hashlib.sha256(
        json.dumps([payload, options], sort_keys=True).encode()
    ).hexdigest()
    base = store.run_dir(state.id) / "paper_orchestra" / fingerprint[:20]
    (base / "reflection").mkdir(parents=True)
    (base / "job.json").write_text(json.dumps({"options": options}))
    (base / "reflection/final_refined_paper.tex").write_text("Completed manuscript")
    (base / "final_paper.pdf").write_bytes(b"%PDF-completed-fixture")
    (base / "retrieved-evidence.json").write_text("[]")
    (base / "completed.json").write_text(
        json.dumps(
            {
                "pdf_sha256": digest(base / "final_paper.pdf"),
                "source_sha256": digest(base / "reflection/final_refined_paper.tex"),
            }
        )
    )
    receipt(base)
    WriterAccounting(base, store, state, fingerprint).reserve_remaining(15)
    (base / "usage.jsonl").write_bytes(line("completed-child", 8))
    monkeypatch.setattr("autoresearch.paper_orchestra.verify_checkout", lambda _: None)
    return store, state, config, base


def test_completed_fast_path_reconciles_before_return_without_relaunch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.paper_orchestra import run_official_writer

    store, state, config, _ = completed_job(tmp_path, monkeypatch)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **kw: pytest.fail("completed writer must not relaunch")
    )
    for _ in range(2):
        text, refs = run_official_writer(state, store, config)
        assert text == "Completed manuscript" and refs == []
    usage = store.usage(state.id)
    assert usage["cost_usd"] == 8
    assert usage["reserved_usd"] == 0
    assert usage["writer_jobs"] == 1
    assert usage["model_calls_attempted"] == 1


def test_completed_fast_path_cannot_release_live_worker_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.paper_orchestra import run_official_writer

    store, state, config, base = completed_job(tmp_path, monkeypatch)
    receipt(base, pid=12345, pgid=12345, exited=True)
    monkeypatch.setattr("autoresearch.paper_orchestra._process_group_running", lambda _: True)
    with pytest.raises(PaperOrchestraError, match="process group"):
        run_official_writer(state, store, config)
    assert store.usage(state.id)["reserved_usd"] == 15
    assert store.usage(state.id)["cost_usd"] == 0


def test_journal_recovery_rejects_symlink(tmp_path: Path) -> None:
    receipt(tmp_path)
    target = tmp_path / "private.jsonl"
    original = b'{"id":"private-torn"'
    target.write_bytes(original)
    (tmp_path / "usage.jsonl").symlink_to(target)
    with pytest.raises(PaperOrchestraError, match="symlink"):
        _recover_writer_journals(tmp_path, {"backend": "local"})
    assert target.read_bytes() == original
