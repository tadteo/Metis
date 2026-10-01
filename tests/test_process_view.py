"""Public synthetic durable execution snapshots; no paid services."""

import json
from pathlib import Path

import pytest

from autoresearch.accounting import SubordinateCall
from autoresearch.contracts import Usage
from autoresearch.engine import Engine
from autoresearch.process_view import process_view
from autoresearch.store import Store


def fixture(tmp_path: Path):
    store = Store(tmp_path)
    state = Engine(store).create("Synthetic process", "Public fixture", demo=True)
    return store, state


def event(store, state, kind, timestamp, **payload):
    store.event(state.id, kind, state.stage.value, payload)
    with store.connect() as db:
        db.execute(
            "UPDATE events SET timestamp=? WHERE seq=(SELECT max(seq) FROM events)", (timestamp,)
        )


def test_parallel_identity_timing_cost_and_reservations(tmp_path):
    store, state = fixture(tmp_path)
    for role, offset in (("critic", "01"), ("producer", "02")):
        event(
            store,
            state,
            "agent_started",
            f"2026-01-01T00:00:{offset}+00:00",
            role=role,
            request_sha256=role,
        )
        call = store.reserve(state.id, role, 1, role)
        store.settle(call, Usage(cost_usd=0.3))
        event(store, state, "agent_completed", "2026-01-01T00:00:10+00:00", call_id=call)
    store.reserve(state.id, "unmatched", 2, "missing")
    result = process_view(store, state.id)
    calls = [r for r in result["rows"] if r["kind"] == "call"]
    assert [r["duration_seconds"] for r in calls] == [9, 8, None]
    assert calls[2]["parent_id"] == "unattributed"
    assert result["usage"]["cost_usd"] == pytest.approx(0.6)
    assert result["usage"]["reserved_usd"] == 2
    for key, value in result["usage"].items():
        assert value == store.usage(state.id)[key]
    assert result["rows"][0]["cost_usd"] == pytest.approx(0.6)


def test_subordinate_costs_explain_parent_and_raw_details_are_private(tmp_path, monkeypatch):
    store, state = fixture(tmp_path)
    secret = "SYNTHETIC_PROVIDER_SECRET_VALUE"  # noqa: S105 - public fixture
    monkeypatch.setenv("XAI_API_KEY", secret)
    parent = store.reserve(state.id, "writer", 1, "parent", kind="aggregate")
    child = SubordinateCall(
        namespace="fixture",
        id="child",
        provider=secret,
        usage=Usage(cost_usd=0.2),
        details={
            "prompt": "PRIVATE_PROMPT",
            "path": "/private/research",
            "output": "PRIVATE_OUTPUT",
        },
    )
    store.settle(parent, Usage(cost_usd=0.5), subordinate_calls=[child])
    result = process_view(store, state.id)
    encoded = json.dumps(result)
    assert all(
        value not in encoded
        for value in (secret, "PRIVATE_PROMPT", "PRIVATE_OUTPUT", "/private/research")
    )
    assert result["rows"][0]["cost_usd"] == 0.5
    row = next(r for r in result["rows"] if r["kind"] == "subordinate_call")
    assert row["cost_usd"] == 0.2 and row["cost_included_in_parent"]
    assert row["duration_seconds"] is None


def test_ambiguous_retries_and_failed_call_do_not_invent_success(tmp_path):
    store, state = fixture(tmp_path)
    for _ in range(2):
        event(
            store,
            state,
            "agent_started",
            "2026-01-01T00:00:00+00:00",
            role="critic",
            request_sha256="same",
        )
        call = store.reserve(state.id, "critic", 0.5, "same")
        store.settle(call, Usage(cost_usd=0.5, estimated=True))
    result = process_view(store, state.id)
    calls = [r for r in result["rows"] if r["kind"] == "call"]
    assert len(calls) == 2
    assert all(
        r["status"] == "unknown" and r["started_at"] is None and r["parent_id"] == "unattributed"
        for r in calls
    )
    assert result["rows"][0]["cost_usd"] == 1
    assert result["rows"][0]["estimated"]


def test_complete_events_reentry_and_failed_experiment(tmp_path):
    store, state = fixture(tmp_path)
    with store.connect() as db:
        db.executemany(
            "INSERT INTO events(run_id,timestamp,kind,stage,payload) VALUES(?,?,?,?,?)",
            [(state.id, "2026-01-01T00:00:00+00:00", "diagnostic", state.stage.value, "{}")] * 2001,
        )
    store.event(state.id, "transition", "baseline", {"from": state.stage.value, "to": "baseline"})
    store.event(state.id, "execution_started", "baseline", {"id": "synthetic-1"})
    store.event(
        state.id,
        "experiment_completed",
        "baseline",
        {
            "id": "synthetic-1",
            "status": "failed",
            "duration_seconds": 3.5,
            "stdout": "PRIVATE_LOG",
            "exit_code": 1,
        },
    )
    store.event(
        state.id, "transition", state.stage.value, {"from": "baseline", "to": state.stage.value}
    )
    result = process_view(store, state.id)
    assert len([r for r in result["rows"] if r["kind"] == "stage_visit"]) == 3
    experiment = next(r for r in result["rows"] if r["kind"] == "experiment")
    assert experiment["status"] == "failed" and experiment["duration_seconds"] == 3.5
    assert experiment["cost_usd"] is None
    assert "PRIVATE_LOG" not in json.dumps(result)


def test_unlinked_start_and_interrupted_execution_remain_unknown(tmp_path):
    store, state = fixture(tmp_path)
    store.event(
        state.id,
        "agent_started",
        state.stage.value,
        {"role": "critic", "request_sha256": "no-reservation"},
    )
    store.event(state.id, "execution_started", state.stage.value, {"id": "interrupted"})
    result = process_view(store, state.id)
    evidence = [r for r in result["rows"] if r["kind"] in {"agent_event", "experiment"}]
    assert len(evidence) == 2
    assert all(
        r["status"] == "unknown" and r["cost_usd"] is None and r["ended_at"] is None
        for r in evidence
    )


def test_process_endpoint_authenticated_read_only(tmp_path):
    import http.client
    import threading

    from autoresearch.web import ResearchServer

    store, state = fixture(tmp_path)
    server = ResearchServer(store, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = store.get_run(state.id).model_dump_json()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        path = f"/api/runs/{state.id}/process"
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 401
        response.read()
        connection.request("GET", path, headers={"Authorization": f"Bearer {server.token}"})
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["current_stage"] == state.stage.value
        connection.close()
        assert store.get_run(state.id).model_dump_json() == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
