"""Public synthetic stage histories, including failed and repeated attempts."""

import json

import pytest

from autoresearch.contracts import Stage
from autoresearch.engine import Engine
from autoresearch.store import ConflictError, Store


def test_engine_reports_each_checkpoint_and_preserves_retry(tmp_path):
    store = Store(tmp_path)
    engine = Engine(store)
    state = engine.create("Synthetic report", "Public fixture", demo=True)
    assert store.stage_reports(state.id) == []
    initial_stage = state.stage
    state = engine.step(state.id)
    first = store.stage_reports(state.id)[0]
    assert first["payload"]["stage"] == initial_stage.value
    assert first["payload"]["checkpoint"] == state.version
    assert first["payload"]["synthetic"] is True
    assert first["payload"]["changes"]["limitations"]
    state.feedback = "Earlier stage feedback"
    store.save(state)
    for kind, status in (
        ("stage_error", "blocked"),
        ("budget_exhausted", "budget_exhausted"),
        ("coding_pending", "waiting"),
        ("workflow_violation", "blocked"),
    ):
        state.error = "Public failure"
        state.status = status
        store.save(state, kind)
    reports = store.stage_reports(state.id)
    assert len(reports) == 5
    assert reports[0] == first
    assert all(not report["payload"]["feedback"] for report in reports[1:])
    assert [report["payload"]["status"] for report in reports[1:]] == [
        "blocked",
        "budget_exhausted",
        "waiting",
        "blocked",
    ]
    assert reports[3]["payload"]["error"] == ""
    store.save(state)  # Administrative checkpoints are not stage attempts.
    assert len(store.stage_reports(state.id)) == 5


def test_report_redaction_rejection_and_atomic_conflict(tmp_path):
    store = Store(tmp_path)
    state = Engine(store).create("Synthetic report", "Public fixture", demo=True)
    config = store.get_config(state.id)
    config.privacy.redact_patterns = ["PRIVATE_FIXTURE"]
    with store.connect() as db:
        db.execute("UPDATE runs SET config=? WHERE id=?", (config.model_dump_json(), state.id))
    stale = state.model_copy(deep=True)
    state.memory.append(
        {"stage": state.stage.value, "decision": "reject", "feedback": "PRIVATE_FIXTURE failed"}
    )
    state.feedback = "PRIVATE_FIXTURE rejected"
    state.stage = Stage.VERIFY_LIMITATIONS
    store.save(state, "transition")
    report = store.stage_reports(state.id)[0]["payload"]
    assert "PRIVATE_FIXTURE" not in json.dumps(report)
    assert report["changes"]["memory"][0]["decision"] == "reject"
    with pytest.raises(ConflictError):
        store.save(stale, "transition")
    assert len(store.stage_reports(state.id)) == 1


def test_report_failure_rolls_back_checkpoint_and_event(tmp_path, monkeypatch):
    store = Store(tmp_path)
    state = Engine(store).create("Synthetic report", "Public fixture", demo=True)
    before = store.events(state.id)

    def fail(*args, **kwargs):
        raise ValueError("synthetic report failure")

    monkeypatch.setattr("autoresearch.store.stage_report", fail)
    with pytest.raises(ValueError):
        store.save(state, "transition")
    assert store.get_run(state.id).version == state.version
    assert store.events(state.id) == before


def test_internal_checkpoint_does_not_erase_attempt_evidence(tmp_path):
    store = Store(tmp_path)

    def handler(state, config, runner):
        state.limitations = ["Synthetic limitation"]
        state.research_protocol = {"note": "Synthetic sealed measurement"}
        store.save(state, "protocol_sealed")
        state.stage = Stage.VERIFY_LIMITATIONS

    engine = Engine(store, stage_handlers={Stage.LIMITATIONS: handler})
    state = engine.create("Synthetic report", "Public fixture", demo=True)
    engine.step(state.id)
    report = store.stage_reports(state.id)[0]["payload"]
    assert report["changes"]["research_protocol"]["note"] == "Synthetic sealed measurement"
    assert report["checkpoint"] == 2


def test_manuscript_identity_and_pending_reason_are_retained(tmp_path):
    store = Store(tmp_path)
    state = Engine(store).create("Synthetic report", "Public fixture", demo=True)
    state.manuscript = "Synthetic draft"
    store.save(state, "transition")
    first = store.stage_reports(state.id)[0]["payload"]
    assert first["changes"]["manuscript"]["bytes"] == 15
    assert len(first["changes"]["manuscript"]["sha256"]) == 64
    state.status = "waiting"
    store.save(state, "coding_pending", {"reason": "Synthetic worker pending"})
    assert store.stage_reports(state.id)[1]["payload"]["reason"] == "Synthetic worker pending"
