"""Crash-recoverable accounting for a writer job's cumulative subordinate budget."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .accounting import SubordinateCall
from .contracts import RunState, Usage
from .paper_orchestra import _usage_rows, _write_json
from .store import Store


class WriterAccounting:
    def __init__(self, base: Path, store: Store, state: RunState, fingerprint: str):
        self.base, self.store, self.state = base, store, state
        self.fingerprint = fingerprint
        self.path = base / "accounting.json"
        self.record: dict[str, Any] = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"schema_version": 1, "attempts": []}
        )
        if self.record.get("schema_version") != 1:
            raise ValueError("Unsupported writer accounting receipt")

    def save(self) -> None:
        _write_json(self.path, self.record)

    def reconcile(self) -> None:
        """Call only after the prior worker has exited; settle once even after a crash."""
        for attempt in self.record["attempts"]:
            if attempt.get("settled"):
                continue
            call = self.store.call_for_request(self.state.id, "paper_orchestra", attempt["key"])
            if call is None:
                # Intent was durable, but the process died before reserving or dispatching.
                attempt["settled"] = True
                self.save()
                continue
            if "usage" not in attempt:
                previous = set(attempt["previous_ids"])
                rows = [
                    r for r in _usage_rows(self.base / "usage.jsonl") if r["id"] not in previous
                ]
                attempt["usage"] = Usage(
                    input_tokens=sum(r.get("input_tokens", 0) for r in rows),
                    output_tokens=sum(r.get("output_tokens", 0) for r in rows),
                    cost_usd=sum(r["cost_usd"] for r in rows),
                    estimated=any(r.get("estimated", False) for r in rows),
                    latency_seconds=sum(r.get("latency_seconds", 0) for r in rows),
                ).model_dump()
                attempt["rows"] = rows
                # Persist the exact settlement before writing immutable Store accounting.
                self.save()
            # Preserve the attempted-call denominator even when settlement stops
            # the run for a cost overrun. Stable child IDs deduplicate replay.
            self.store.settle(
                call["id"],
                Usage.model_validate(attempt["usage"]),
                subordinate_calls=[
                    SubordinateCall.from_record("paper_orchestra", row) for row in attempt["rows"]
                ],
                stage=self.state.stage,
            )
            attempt["settled"] = True
            self.save()

    def reserve_remaining(self, maximum: float) -> str:
        if any(not a.get("settled") for a in self.record["attempts"]):
            raise ValueError("Reconcile the previous writer attempt before dispatch")
        rows = _usage_rows(self.base / "usage.jsonl")
        remaining = max(0.0, maximum - sum(r["cost_usd"] for r in rows))
        key = hashlib.sha256(
            f"{self.fingerprint}:attempt:{len(self.record['attempts'])}".encode()
        ).hexdigest()
        attempt: dict[str, Any] = {"key": key, "previous_ids": [r["id"] for r in rows]}
        self.record["attempts"].append(attempt)
        self.save()
        # The durable key recovers a reservation even if the parent dies before receiving its ID.
        return self.store.reserve(
            self.state.id, "paper_orchestra", remaining, key, kind="aggregate", idempotent=True
        )
