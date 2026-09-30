"""Acquisition is a bounded, content-addressed tool, with durable recovery."""

import hashlib

import httpx
import pytest

from autoresearch.coding import CodingAction, CodingSession
from autoresearch.config import ResearchConfig
from autoresearch.contracts import RunState, Stage
from autoresearch.runtime_support import ExecutionError
from autoresearch.store import Store


def session(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    config = ResearchConfig()
    store = Store(tmp_path / "private")
    state = RunState(
        id="0123456789ab", title="Public fixture", objective="Acquire data", stage=Stage.BASELINE
    )
    store.create(state, config)
    return CodingSession(
        state, lambda *_: pytest.fail("no model call"), store, config, {"source_dir": str(source)}
    )


def transport(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(
        "autoresearch.acquisition.httpx.Client",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_acquisition_retains_hash_and_retry_reuses_exact_bytes(tmp_path, monkeypatch):
    task = session(tmp_path)
    count = []
    data = b"public fixture data"
    transport(
        monkeypatch,
        lambda request: (count.append(request.url) or httpx.Response(200, content=data)),
    )
    action = CodingAction(
        tool="acquire", url="https://raw.githubusercontent.com/example/data", path="data/labels.bin"
    )
    first = task.observation(action)
    assert first["receipt"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert task.observation(action) == first and len(count) == 1
    (task.root / action.path).write_bytes(b"conflicting data")
    with pytest.raises(ExecutionError, match="conflicting"):
        task.observation(action)


def test_acquisition_interruption_recovers_checkpointed_export(tmp_path, monkeypatch):
    task = session(tmp_path)
    data = b"fixture"
    transport(monkeypatch, lambda request: httpx.Response(200, content=data))
    import autoresearch.acquisition as acquisition

    original = acquisition.os.replace

    def interrupt(source, target, **kwargs):
        original(source, target, **kwargs)
        if str(source).startswith(".autoresearch-acquire-"):
            raise RuntimeError("simulated interruption after materialization")

    monkeypatch.setattr(acquisition.os, "replace", interrupt)
    action = CodingAction(
        tool="acquire", url="https://raw.githubusercontent.com/example/data", path="data.bin"
    )
    with pytest.raises(RuntimeError, match="interruption"):
        task.observation(action)
    monkeypatch.setattr(acquisition.os, "replace", original)
    restored = CodingSession(task.state, task.call, task.store, task.config, task.context)
    result = restored.observation(action)
    assert len(restored.record["resources"]) == 1
    assert result["materialized"] == restored.record["resources"]
    assert (restored.root / action.path).read_bytes() == data


def test_acquisition_network_errors_are_tool_feedback_and_private_hosts_are_refused(
    tmp_path, monkeypatch
):
    task = session(tmp_path)
    transport(monkeypatch, lambda request: httpx.Response(404))
    with pytest.raises(ExecutionError, match="acquisition failed"):
        task.observation(
            CodingAction(
                tool="acquire", url="https://raw.githubusercontent.com/missing", path="missing"
            )
        )
    with pytest.raises(ExecutionError, match="not permitted"):
        task.observation(
            CodingAction(tool="acquire", url="http://127.0.0.1/private", path="private")
        )
    assert not (task.root / "missing").exists()


def test_repository_archive_requires_immutable_revision(tmp_path):
    task = session(tmp_path)
    with pytest.raises(ExecutionError, match="40-character commit"):
        task.observation(
            CodingAction(
                tool="acquire",
                url="https://codeload.github.com/example/repo/zip/main",
                path="repo",
                archive=True,
                revision="main",
            )
        )


def test_materialize_accepts_matching_inherited_file_and_rejects_conflict(tmp_path, monkeypatch):
    from autoresearch.acquisition import materialize

    task = session(tmp_path)
    data = b"public supplied dataset"
    transport(monkeypatch, lambda request: httpx.Response(200, content=data))
    action = CodingAction(
        tool="acquire", url="https://raw.githubusercontent.com/example/data", path="labels.bin"
    )
    entries = task.observation(action)["materialized"]
    destination = tmp_path / "experiment"
    destination.mkdir()
    (destination / "labels.bin").write_bytes(data)
    materialize(task.store.run_dir(task.state.id), destination, entries)
    assert (destination / "labels.bin").read_bytes() == data
    (destination / "labels.bin").write_bytes(b"different")
    with pytest.raises(ExecutionError, match="conflicts"):
        materialize(task.store.run_dir(task.state.id), destination, entries)
