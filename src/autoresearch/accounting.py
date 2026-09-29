"""Generic subordinate model-call facts and explicit legacy accounting migration."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from .contracts import Model, Usage
from .privacy import redact

ReservationKind = Literal["model", "aggregate"]


class SubordinateCall(Model):
    """One attempted API call whose usage is charged by an aggregate reservation.

    Namespaces distinguish adapter identity spaces. IDs must remain stable across
    recovery, and must identify attempts rather than cached response lookups.
    """

    namespace: str = Field(min_length=1, max_length=256)
    id: str = Field(min_length=1, max_length=256)
    provider: str = ""
    model: str = ""
    request_hash: str = ""
    status: str = Field(default="completed", min_length=1)
    usage: Usage = Field(default_factory=Usage)
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, namespace: str, record: dict[str, Any]) -> SubordinateCall:
        """Adapt a durable SDK journal row while retaining its original details."""
        return cls(
            namespace=namespace,
            id=record["id"],
            provider=record.get("provider", ""),
            model=record.get("model", ""),
            request_hash=record.get("request_hash", ""),
            status=record.get("status", "completed"),
            usage=Usage.model_validate(
                {key: record[key] for key in Usage.model_fields if key in record}
            ),
            details=record,
        )


def matches_legacy_record(
    imported: SubordinateCall, actual: SubordinateCall, patterns: list[str]
) -> bool:
    """Match an old sanitized diagnostic fact to its raw private SDK journal.

    A matching projection can restore redacted descriptive fields, but cannot
    change child identity or accounting usage. Newly journaled records never use
    this reconciliation path. Original diagnostic events remain immutable.
    """
    if (imported.namespace, imported.id, imported.usage) != (
        actual.namespace,
        actual.id,
        actual.usage,
    ):
        return False
    try:
        if actual != SubordinateCall.from_record(actual.namespace, actual.details):
            return False
        sanitized = SubordinateCall.from_record(actual.namespace, redact(actual.details, patterns))
    except (KeyError, TypeError, ValueError):
        return False
    return imported == sanitized


def migrate_accounting(db: sqlite3.Connection) -> None:
    """Import pre-ledger accounting once, without rewriting historical events.

    Old child events did not identify their parent reservation. Preserve the
    relationship as NULL rather than guessing among multiple writer jobs. A
    matching later adapter replay may establish that association explicitly.
    """
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    migration = "aggregate_accounting_v1"
    if db.execute("SELECT 1 FROM schema_migrations WHERE name=?", (migration,)).fetchone():
        return
    columns = {row["name"] for row in db.execute("PRAGMA table_info(calls)")}
    if "kind" not in columns:
        db.execute(
            "ALTER TABLE calls ADD COLUMN kind TEXT NOT NULL DEFAULT 'model' "
            "CHECK(kind IN ('model','aggregate'))"
        )
    db.execute("""
        CREATE TABLE IF NOT EXISTS subordinate_calls(
            run_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            child_id TEXT NOT NULL,
            parent_id TEXT,
            record TEXT NOT NULL,
            origin TEXT NOT NULL,
            PRIMARY KEY(run_id,namespace,child_id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS subordinate_parent ON subordinate_calls(parent_id)")
    db.execute("CREATE INDEX IF NOT EXISTS calls_run_kind ON calls(run_id,kind)")
    # This is the only adapter-specific interpretation of the historical schema.
    db.execute("UPDATE calls SET kind='aggregate' WHERE role='paper_orchestra'")
    events = db.execute(
        "SELECT seq,run_id,payload FROM events WHERE kind='paper_orchestra_api_call' ORDER BY seq"
    ).fetchall()
    offsets: dict[str, int] = {}
    for event in events:
        run_id = event["run_id"]
        index = offsets.get(run_id, 0)
        offsets[run_id] = index + 1
        record = json.loads(event["payload"])
        record.setdefault("id", str(index))
        child = SubordinateCall.from_record("paper_orchestra", record)
        # Historical usage counted unique IDs; its last event provided details.
        # Original duplicate events are deliberately retained for audit.
        db.execute(
            "INSERT INTO subordinate_calls VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(run_id,namespace,child_id) DO UPDATE SET record=excluded.record",
            (run_id, child.namespace, child.id, None, child.model_dump_json(), "legacy_event"),
        )
    db.execute(
        "INSERT INTO schema_migrations VALUES(?,?)", (migration, datetime.now(UTC).isoformat())
    )
