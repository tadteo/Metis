"""Read-only execution projection; diagnostic timestamps are not invented spans."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from .privacy import redact
from .store import Store, now


def _duration(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        value = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        return value if value >= 0 else None
    except (ValueError, TypeError):
        return None


def _row(identity: str, parent: str | None, kind: str, label: str, **values: Any) -> dict[str, Any]:
    return {
        "id": identity,
        "parent_id": parent,
        "kind": kind,
        "label": label,
        "stage": None,
        "status": "unknown",
        "started_at": None,
        "ended_at": None,
        "duration_seconds": None,
        "cost_usd": 0.0,
        "reserved_usd": 0.0,
        "estimated": False,
        "event_seq": None,
        "record": {},
        "timing_basis": "unavailable",
        "cost_included_in_parent": True,
        **values,
    }


def process_view(store: Store, run_id: str, *, working: bool = False) -> dict[str, Any]:
    """Return one complete ledger snapshot, without triggering work or reading artifacts.

    Only unambiguous request identity links diagnostics to reservations. Settled
    billing alone says nothing about successful execution. Time between stage
    transitions includes pauses and waiting; no model-call duration is inferred
    from that interval. SDK details and research text are intentionally omitted.
    """
    with store.connect() as db:
        db.execute("BEGIN")
        run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise KeyError("run not found")
        state, config = json.loads(run["state"]), json.loads(run["config"])
        events = [
            {**dict(row), "payload": json.loads(row["payload"])}
            for row in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,))
        ]
        calls = [
            dict(row)
            for row in db.execute("SELECT * FROM calls WHERE run_id=? ORDER BY rowid", (run_id,))
        ]
        children = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM subordinate_calls WHERE run_id=? ORDER BY rowid", (run_id,)
            )
        ]
        captured = now()
    status = (
        "pausing"
        if working and run["paused"]
        else "running"
        if working
        else "paused"
        if run["paused"]
        else state["status"]
    )
    root = _row(
        "run",
        None,
        "run",
        "Research run",
        status=status,
        stage=state["stage"],
        started_at=state["created_at"],
        timing_basis="run_wall_clock",
    )
    terminal = state["status"] in {"completed", "failed", "stopped", "done"}
    terminal_times = [
        event["timestamp"]
        for event in events
        if event["kind"] == "transition"
        and event["payload"].get("status") in {"completed", "failed", "stopped", "done"}
        and event["payload"].get("to") == state["stage"]
    ]
    root["ended_at"] = (
        max([state["updated_at"], *terminal_times], key=datetime.fromisoformat)
        if terminal
        else None
    )
    root["duration_seconds"] = _duration(root["started_at"], root["ended_at"] or captured)
    rows = [root]
    visits: dict[int, dict[str, Any]] = {}
    first_stage = events[0]["stage"] if events else state["stage"]
    visit = _row(
        "visit:0",
        "run",
        "stage_visit",
        first_stage.replace("_", " "),
        stage=first_stage,
        started_at=state["created_at"],
        timing_basis="stage_wall_clock",
    )
    rows.append(visit)
    for event in events:
        visits[event["seq"]] = visit
        payload = event["payload"]
        if event["kind"] in {"stage_error", "workflow_violation", "budget_exhausted"}:
            visit["record"] = {"last_failure_kind": event["kind"], "last_failure_seq": event["seq"]}
        if event["kind"] == "transition":
            visit.update(status="completed", ended_at=event["timestamp"])
            visit["duration_seconds"] = _duration(visit["started_at"], visit["ended_at"])
            stage = payload.get("to", event["stage"])
            visit = _row(
                f"visit:{event['seq']}",
                "run",
                "stage_visit",
                stage.replace("_", " "),
                stage=stage,
                started_at=event["timestamp"],
                event_seq=event["seq"],
                timing_basis="stage_wall_clock",
            )
            rows.append(visit)
    visit.update(status=status, ended_at=root["ended_at"])
    visit["duration_seconds"] = _duration(visit["started_at"], visit["ended_at"] or captured)
    unknown = _row("unattributed", "run", "unattributed", "Unattributed records", status="unknown")
    rows.append(unknown)
    identities = Counter((c["role"], c["request_hash"]) for c in calls)
    call_rows: dict[str, dict[str, Any]] = {}
    linked_starts: set[int] = set()
    usage: dict[str, Any] = {
        "cost_usd": 0.0,
        "reserved_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "calls": len(calls),
        "aggregate_jobs": sum(c["kind"] == "aggregate" for c in calls),
        "subordinate_calls": len(children),
        "model_calls_attempted": sum(c["kind"] == "model" for c in calls) + len(children),
        "budget_usd": config["budget"]["usd"],
    }
    for call in calls:
        identity = (call["role"], call["request_hash"])
        starts = (
            [
                e
                for e in events
                if e["kind"] == "agent_started"
                and (e["payload"].get("role"), e["payload"].get("request_sha256")) == identity
            ]
            if identities[identity] == 1
            else []
        )
        ends = [
            e
            for e in events
            if e["kind"] in {"agent_completed", "agent_provider_failed"}
            and e["payload"].get("call_id") == call["id"]
        ]
        start = starts[0] if len(starts) == 1 else None
        end = ends[0] if len(ends) == 1 else None
        if start and end and (end["seq"] < start["seq"] or end["stage"] != start["stage"]):
            start = None
        if start:
            linked_starts.add(start["seq"])
        evidence = start or end
        parent = (
            visits[evidence["seq"]]
            if evidence and visits[evidence["seq"]]["stage"] == evidence["stage"]
            else unknown
        )
        amount = json.loads(call["usage"])
        held = call["reserved"] if call["status"] == "reserved" else 0.0
        row = _row(
            f"call:{call['id']}",
            parent["id"],
            "call",
            call["role"].replace("_", " "),
            stage=parent["stage"],
            status=("failed" if end["kind"] == "agent_provider_failed" else "completed")
            if end
            else "reserved"
            if held or call["status"] == "reserved"
            else "unknown",
            started_at=start["timestamp"] if start else None,
            ended_at=end["timestamp"] if end else None,
            cost_usd=amount.get("cost_usd", 0.0),
            reserved_usd=held,
            estimated=amount.get("estimated", False),
            event_seq=evidence["seq"] if evidence else None,
            record={
                "call_id": call["id"],
                "role": call["role"],
                "reservation_kind": call["kind"],
                "accounting_status": call["status"],
                "input_tokens": amount.get("input_tokens", 0),
                "output_tokens": amount.get("output_tokens", 0),
            },
        )
        for source in (start, end):
            if source:
                row["record"].update(
                    {
                        key: source["payload"][key]
                        for key in ("model", "provider", "agent")
                        if key in source["payload"]
                    }
                )
        agent_index = row["record"].get("agent")
        if isinstance(agent_index, int):
            row["label"] += f" · agent {agent_index + 1}"
        row["duration_seconds"] = _duration(row["started_at"], row["ended_at"])
        row["timing_basis"] = (
            "agent_events"
            if start and end
            else "partial_agent_events"
            if evidence
            else "unavailable"
        )
        rows.append(row)
        call_rows[call["id"]] = row
        for total in (parent, root):
            total["cost_usd"] += row["cost_usd"]
            total["reserved_usd"] += held
            total["estimated"] |= row["estimated"]
        for key in ("cost_usd", "input_tokens", "output_tokens"):
            usage[key] += amount.get(key, 0)
        usage["reserved_usd"] += held
    for event in events:
        if event["kind"] == "agent_started" and event["seq"] not in linked_starts:
            parent = visits[event["seq"]]
            rows.append(
                _row(
                    f"diagnostic:{event['seq']}",
                    parent["id"],
                    "agent_event",
                    "Unlinked agent start",
                    stage=event["stage"],
                    started_at=event["timestamp"],
                    cost_usd=None,
                    event_seq=event["seq"],
                    timing_basis="partial_agent_events",
                    record={
                        "role": event["payload"].get("role"),
                        "attribution": "No unambiguous reservation link",
                    },
                )
            )
    for child in children:
        record = json.loads(child["record"])
        parent = call_rows.get(child["parent_id"], unknown)
        amount = record["usage"]
        rows.append(
            _row(
                f"child:{child['namespace']}:{child['child_id']}",
                parent["id"],
                "subordinate_call",
                record.get("model") or record["namespace"],
                stage=parent["stage"],
                status=record["status"],
                cost_usd=amount["cost_usd"],
                estimated=amount.get("estimated", False),
                record={
                    "namespace": record["namespace"],
                    "child_id": record["id"],
                    "provider": record["provider"],
                    "model": record["model"],
                    "parent_status": "associated"
                    if child["parent_id"]
                    else "unassociated_legacy_event",
                    "input_tokens": amount["input_tokens"],
                    "output_tokens": amount["output_tokens"],
                },
            )
        )
    # Preserve every recorded execution receipt, including failures and repeated attempts.
    for event in events:
        if event["kind"] != "experiment_completed":
            continue
        receipt = event["payload"]
        starts = [
            e
            for e in events
            if e["kind"] == "execution_started"
            and e["payload"].get("id") == receipt.get("id")
            and e["seq"] < event["seq"]
        ]
        start = starts[0] if len(starts) == 1 else None
        parent = visits[event["seq"]]
        rows.append(
            _row(
                f"experiment:{event['seq']}",
                parent["id"],
                "experiment",
                f"Experiment {receipt.get('id', '')}",
                stage=event["stage"],
                status=receipt.get("status", "unknown"),
                started_at=start["timestamp"] if start else None,
                ended_at=event["timestamp"],
                duration_seconds=receipt.get("duration_seconds"),
                cost_usd=None,
                event_seq=event["seq"],
                timing_basis="execution_receipt",
                record={
                    key: receipt[key]
                    for key in ("id", "status", "exit_code", "duration_seconds")
                    if key in receipt
                },
            )
        )
    recorded_experiments = {
        e["payload"].get("id") for e in events if e["kind"] == "experiment_completed"
    }
    for receipt in state.get("experiments", []):
        if receipt["id"] in recorded_experiments:
            continue
        starts = [
            event
            for event in events
            if event["kind"] == "execution_started" and event["payload"].get("id") == receipt["id"]
        ]
        start = starts[0] if len(starts) == 1 else None
        parent = (
            visits[start["seq"]]
            if start and visits[start["seq"]]["stage"] == start["stage"]
            else unknown
        )
        rows.append(
            _row(
                f"experiment:legacy:{receipt['id']}",
                parent["id"],
                "experiment",
                f"Experiment {receipt['id']}",
                status=receipt["status"],
                stage=parent["stage"],
                started_at=start["timestamp"] if start else None,
                event_seq=start["seq"] if start else None,
                duration_seconds=receipt.get("duration_seconds"),
                cost_usd=None,
                timing_basis="execution_receipt",
                record={
                    "id": receipt["id"],
                    "status": receipt["status"],
                    "exit_code": receipt.get("exit_code"),
                },
            )
        )
        recorded_experiments.add(receipt["id"])
    for event in events:
        if (
            event["kind"] != "execution_started"
            or event["payload"].get("id") in recorded_experiments
        ):
            continue
        identity = event["payload"].get("id")
        pending = state.get("pending_experiment") or {}
        parent = visits[event["seq"]]
        rows.append(
            _row(
                f"experiment:started:{event['seq']}",
                parent["id"],
                "experiment",
                f"Experiment {identity}",
                stage=event["stage"],
                status="pending" if pending.get("id") == identity else "unknown",
                started_at=event["timestamp"],
                cost_usd=None,
                event_seq=event["seq"],
                timing_basis="partial_execution_events",
                record={"id": identity},
            )
        )
    if not any(row["parent_id"] == "unattributed" for row in rows):
        rows.remove(unknown)
    result: dict[str, Any] = redact(
        {
            "schema_version": 1,
            "captured_at": captured,
            "current_stage": state["stage"],
            "rows": rows,
            "usage": usage,
            "notes": [
                "Costs use configured rates, not invoices; compute and external fees are excluded.",
                "Stage and run wall time includes pauses and waiting. Missing call timing is unavailable.",
                "Parent totals include child costs; subordinate receipts are explanatory, never additional charges.",
                "Settled calls without completion evidence have unknown execution outcome.",
            ],
        },
        config.get("privacy", {}).get("redact_patterns", []),
    )
    return result
