"""Private SQLite journal, atomic checkpoints, leases and budget reservations."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .accounting import ReservationKind, SubordinateCall, matches_legacy_record, migrate_accounting
from .config import ResearchConfig
from .contracts import RunState, Usage
from .errors import BudgetExceeded as BudgetExceeded
from .privacy import redact
from .runtime_support import parent_descriptor


def now() -> str:
    return datetime.now(UTC).isoformat()


class ConflictError(RuntimeError):
    pass


class Store:
    def __init__(self, root: Path | None = None):
        self.root = (
            (
                root
                or Path(
                    os.environ.get("AUTORESEARCH_HOME", Path.home() / ".local/state/autoresearch")
                )
            )
            .expanduser()
            .resolve()
        )
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.db_path = self.root / "research.sqlite3"
        if self.db_path.is_symlink():
            raise ValueError("runtime database must not be a symlink")
        self._lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, state TEXT NOT NULL, config TEXT NOT NULL, version INTEGER NOT NULL, paused INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, timestamp TEXT NOT NULL, kind TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_run ON events(run_id,seq);
                CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL, reserved REAL NOT NULL, usage TEXT NOT NULL, request_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, response TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS leases(run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, pid INTEGER NOT NULL, host TEXT NOT NULL);
            """)
            migrate_accounting(db)
        os.chmod(self.db_path, 0o600)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def run_dir(self, run_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{12}", run_id):
            raise ValueError("invalid run identifier")
        path = self.root / "runs" / run_id
        if path.is_symlink() or (self.root / "runs").is_symlink():
            raise ValueError("runtime path must not be a symlink")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def create(self, state: RunState, config: ResearchConfig) -> RunState:
        self.run_dir(state.id)
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(id,state,config,version) VALUES(?,?,?,?)",
                (state.id, state.model_dump_json(), config.model_dump_json(), state.version),
            )
        self.event(
            state.id, "run_created", state.stage, {"title": state.title, "mode": config.mode}
        )
        return state

    def get_run(self, run_id: str) -> RunState:
        with self.connect() as db:
            row = db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("run not found")
        return RunState.model_validate_json(row["state"])

    def get_config(self, run_id: str) -> ResearchConfig:
        with self.connect() as db:
            row = db.execute("SELECT config FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("run not found")
        return ResearchConfig.model_validate_json(row["config"])

    def list_runs(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT state FROM runs ORDER BY rowid DESC").fetchall()
        result = []
        for row in rows:
            state = RunState.model_validate_json(row["state"])
            result.append(
                {
                    "id": state.id,
                    "title": state.title,
                    "stage": state.stage.value,
                    "status": "paused" if self.is_paused(state.id) else state.status,
                    "updated_at": state.updated_at,
                    "cost_usd": self.usage(state.id)["cost_usd"],
                }
            )
        return result

    def save(
        self, state: RunState, kind: str = "checkpoint", payload: dict[str, Any] | None = None
    ) -> None:
        previous_version = state.version
        next_version = previous_version + 1
        updated_at = now()
        config = self.get_config(state.id)
        data = redact(
            payload or {"status": state.status, "outcome": state.outcome},
            config.privacy.redact_patterns,
        )
        checkpoint = state.model_copy(update={"version": next_version, "updated_at": updated_at})
        with self.connect() as db:
            cur = db.execute(
                "UPDATE runs SET state=?, version=? WHERE id=? AND version=?",
                (checkpoint.model_dump_json(), next_version, state.id, previous_version),
            )
            if cur.rowcount != 1:
                raise ConflictError("run changed concurrently; reload checkpoint")
            db.execute(
                "INSERT INTO events(run_id,timestamp,kind,stage,payload) VALUES(?,?,?,?,?)",
                (state.id, now(), kind, state.stage.value, json.dumps(data)),
            )
        state.version, state.updated_at = next_version, updated_at

    def event(self, run_id: str, kind: str, stage: str, payload: dict[str, Any]) -> None:
        config = self.get_config(run_id)
        # Event metadata always removes known secrets, including in full trace mode.
        cleaned = redact(payload, config.privacy.redact_patterns)
        if config.privacy.traces == "metadata" and kind.startswith("agent_"):
            cleaned = {
                k: v
                for k, v in cleaned.items()
                if k not in {"prompt", "system", "output", "feedback"}
            }
        with self.connect() as db:
            db.execute(
                "INSERT INTO events(run_id,timestamp,kind,stage,payload) VALUES(?,?,?,?,?)",
                (run_id, now(), kind, stage, json.dumps(cleaned)),
            )

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 2000",
                (run_id, after),
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def set_paused(self, run_id: str, paused: bool) -> None:
        self.get_run(run_id)
        with self.connect() as db:
            db.execute("UPDATE runs SET paused=? WHERE id=?", (int(paused), run_id))

    def is_paused(self, run_id: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT paused FROM runs WHERE id=?", (run_id,)).fetchone()
        return bool(row and row["paused"])

    @contextlib.contextmanager
    def lease(self, run_id: str) -> Iterator[None]:
        import socket

        owner, pid, host = uuid.uuid4().hex, os.getpid(), socket.gethostname()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM leases WHERE run_id=?", (run_id,)).fetchone()
            if row:
                alive = True
                if row["host"] == host:
                    try:
                        os.kill(row["pid"], 0)
                    except ProcessLookupError:
                        alive = False
                if alive:
                    raise ConflictError("another worker owns this run")
                db.execute("DELETE FROM leases WHERE run_id=?", (run_id,))
            db.execute("INSERT INTO leases VALUES(?,?,?,?)", (run_id, owner, pid, host))
        try:
            yield
        finally:
            with self.connect() as db:
                db.execute("DELETE FROM leases WHERE run_id=? AND owner=?", (run_id, owner))

    @staticmethod
    def _attempted_calls(db: sqlite3.Connection, run_id: str) -> int:
        direct = db.execute(
            "SELECT count(*) FROM calls WHERE run_id=? AND kind='model'", (run_id,)
        ).fetchone()[0]
        children = db.execute(
            "SELECT count(*) FROM subordinate_calls WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        return int(direct + children)

    def reserve(
        self,
        run_id: str,
        role: str,
        maximum: float,
        request_hash: str,
        *,
        kind: ReservationKind = "model",
        idempotent: bool = False,
    ) -> str:
        """Reserve a direct call or an adapter's aggregate maximum charge.

        Aggregate adapters must enforce their subordinate call cap before sending
        requests; this monetary reservation does not authorize unlimited calls.
        Idempotent recovery also returns settled calls; it never authorizes resending.
        """
        if isinstance(maximum, bool) or not math.isfinite(maximum) or maximum < 0:
            raise ValueError("budget reservation must be finite and nonnegative")
        if kind not in {"model", "aggregate"}:
            raise ValueError("unknown reservation kind")
        config = self.get_config(run_id)
        call_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if idempotent:
                existing = db.execute(
                    "SELECT id,reserved,kind FROM calls WHERE run_id=? AND role=? AND request_hash=?",
                    (run_id, role, request_hash),
                ).fetchall()
                if len(existing) > 1:
                    raise ConflictError("ambiguous prior reservations require reconciliation")
                if existing:
                    if existing[0]["reserved"] != maximum or existing[0]["kind"] != kind:
                        raise ConflictError("idempotent reservation amount or kind changed")
                    return str(existing[0]["id"])
            rows = db.execute(
                "SELECT status,reserved,usage FROM calls WHERE run_id=?", (run_id,)
            ).fetchall()
            spent = sum(float(json.loads(r["usage"]).get("cost_usd", 0)) for r in rows)
            held = sum(r["reserved"] for r in rows if r["status"] == "reserved")
            attempted_calls = self._attempted_calls(db, run_id)
            if (
                spent + held + maximum > config.budget.usd
                or attempted_calls >= config.budget.max_calls
            ):
                raise BudgetExceeded(
                    "model budget reached; raise budget explicitly before resuming"
                )
            db.execute(
                "INSERT INTO calls(id,run_id,role,status,reserved,usage,request_hash,kind) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (call_id, run_id, role, "reserved", maximum, "{}", request_hash, kind),
            )
        return call_id

    def call_for_request(self, run_id: str, role: str, request_hash: str) -> dict[str, Any] | None:
        """Recover one durable reservation; never guess among duplicate historical calls."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,status,reserved,usage,kind FROM calls WHERE run_id=? AND role=? AND request_hash=?",
                (run_id, role, request_hash),
            ).fetchall()
        if len(rows) > 1:
            raise ConflictError("ambiguous prior reservations require reconciliation")
        return dict(rows[0]) if rows else None

    def settle(
        self,
        call_id: str,
        usage: Usage,
        *,
        subordinate_calls: list[SubordinateCall] | None = None,
        stage: str = "",
    ) -> None:
        """Atomically settle one charge and retain independently identified attempts.

        Child token/cost records are explanatory facts, never additional charges.
        Conflicting replays cannot overwrite either the parent's bill or its
        children. Incurred overspend is committed before raising BudgetExceeded.
        """
        usage = Usage.model_validate(usage.model_dump())
        children = [
            SubordinateCall.model_validate(child.model_dump()) for child in subordinate_calls or []
        ]
        encoded = usage.model_dump_json()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if row is None:
                raise KeyError("budget reservation not found")
            if row["status"] == "settled" and json.loads(row["usage"]) != usage.model_dump():
                raise ConflictError("a settled model call cannot be overwritten")
            if children and row["kind"] != "aggregate":
                raise ValueError("subordinate calls require an aggregate reservation")
            run_id = row["run_id"]
            config_row = db.execute("SELECT config FROM runs WHERE id=?", (run_id,)).fetchone()
            config = ResearchConfig.model_validate_json(config_row["config"])
            added = 0
            for child in children:
                existing = db.execute(
                    "SELECT parent_id,record,origin FROM subordinate_calls "
                    "WHERE run_id=? AND namespace=? AND child_id=?",
                    (run_id, child.namespace, child.id),
                ).fetchone()
                if existing is not None:
                    if json.loads(existing["record"]) != child.model_dump(mode="json"):
                        if existing["origin"] != "legacy_event" or not matches_legacy_record(
                            SubordinateCall.model_validate_json(existing["record"]),
                            child,
                            config.privacy.redact_patterns,
                        ):
                            raise ConflictError("a subordinate model call cannot be overwritten")
                        # One-time restoration from a matching raw journal;
                        # the original sanitized events remain intact.
                        db.execute(
                            "UPDATE subordinate_calls SET record=?,origin='legacy_reconciled' "
                            "WHERE run_id=? AND namespace=? AND child_id=?",
                            (child.model_dump_json(), run_id, child.namespace, child.id),
                        )
                    if existing["parent_id"] not in {None, call_id}:
                        raise ConflictError(
                            "subordinate model call already belongs to another reservation"
                        )
                    if existing["parent_id"] is None:
                        db.execute(
                            "UPDATE subordinate_calls SET parent_id=? "
                            "WHERE run_id=? AND namespace=? AND child_id=?",
                            (call_id, run_id, child.namespace, child.id),
                        )
                    continue
                db.execute(
                    "INSERT INTO subordinate_calls VALUES(?,?,?,?,?,?)",
                    (
                        run_id,
                        child.namespace,
                        child.id,
                        call_id,
                        child.model_dump_json(),
                        "adapter",
                    ),
                )
                added += 1
                payload = redact(
                    {"parent_id": call_id, **child.model_dump(mode="json")},
                    config.privacy.redact_patterns,
                )
                db.execute(
                    "INSERT INTO events(run_id,timestamp,kind,stage,payload) VALUES(?,?,?,?,?)",
                    (run_id, now(), "subordinate_model_call", stage, json.dumps(payload)),
                )
            child_rows = db.execute(
                "SELECT record FROM subordinate_calls WHERE parent_id=?", (call_id,)
            ).fetchall()
            child_usage = [
                SubordinateCall.model_validate_json(child["record"]).usage for child in child_rows
            ]
            if (
                sum(child.cost_usd for child in child_usage) > usage.cost_usd + 1e-9
                or sum(child.input_tokens for child in child_usage) > usage.input_tokens
                or sum(child.output_tokens for child in child_usage) > usage.output_tokens
                or (any(child.estimated for child in child_usage) and not usage.estimated)
            ):
                raise ConflictError("aggregate usage cannot understate its subordinate calls")
            if row["status"] != "settled":
                db.execute(
                    "UPDATE calls SET status='settled',usage=? WHERE id=?", (encoded, call_id)
                )
            overspent = row["status"] != "settled" and usage.cost_usd > row["reserved"] + 1e-9
            excess_calls = added > 0 and self._attempted_calls(db, run_id) > config.budget.max_calls
        if overspent or excess_calls:
            raise BudgetExceeded(
                "reported model cost exceeded its reservation or call limit; actual usage was recorded"
            )

    def subordinate_calls(self, run_id: str) -> list[dict[str, Any]]:
        """Inspect durable child facts, including unresolved historical parentage."""
        self.get_run(run_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM subordinate_calls WHERE run_id=? ORDER BY rowid", (run_id,)
            ).fetchall()
        return [
            {
                **json.loads(row["record"]),
                "parent_id": row["parent_id"],
                "parent_status": "associated" if row["parent_id"] else "unassociated_legacy_event",
                "origin": row["origin"],
            }
            for row in rows
        ]

    def usage(self, run_id: str) -> dict[str, Any]:
        config = self.get_config(run_id)
        with self.connect() as db:
            db.execute("BEGIN")
            rows = db.execute("SELECT * FROM calls WHERE run_id=?", (run_id,)).fetchall()
            attempted = self._attempted_calls(db, run_id)
            children = db.execute(
                "SELECT count(*) FROM subordinate_calls WHERE run_id=?", (run_id,)
            ).fetchone()[0]
        aggregate_jobs = sum(row["kind"] == "aggregate" for row in rows)
        result: dict[str, Any] = {
            "cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": len(rows),
            "reserved_usd": 0.0,
            "budget_usd": config.budget.usd,
            "subordinate_calls": children,
            "model_calls_attempted": attempted,
            "aggregate_jobs": aggregate_jobs,
            # Deprecated compatibility alias; new adapters need not be writers.
            "writer_jobs": aggregate_jobs,
        }
        for row in rows:
            usage = json.loads(row["usage"])
            for key in ("cost_usd", "input_tokens", "output_tokens"):
                result[key] += usage.get(key, 0)
            if row["status"] == "reserved":
                result["reserved_usd"] += row["reserved"]
        return result

    def update_budget(
        self,
        run_id: str,
        *,
        usd: float | None = None,
        max_calls: int | None = None,
        max_experiments: int | None = None,
        wall_seconds: int | None = None,
    ) -> ResearchConfig:
        with self.lease(run_id):
            config = self.get_config(run_id)
            fields = {
                "usd": usd,
                "max_calls": max_calls,
                "max_experiments": max_experiments,
                "wall_seconds": wall_seconds,
            }
            changes = {key: value for key, value in fields.items() if value is not None}
            if not changes:
                raise ValueError("provide at least one budget limit")
            config.budget = type(config.budget).model_validate(
                {**config.budget.model_dump(), **changes}
            )
            with self.connect() as db:
                db.execute(
                    "UPDATE runs SET config=? WHERE id=?", (config.model_dump_json(), run_id)
                )
            self.event(run_id, "budget_updated", self.get_run(run_id).stage, changes)
            return config

    def outstanding_calls(self, run_id: str) -> list[dict[str, Any]]:
        """Unsettled calls include zero-cost holds that still require reconciliation."""
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,role,request_hash,reserved,status FROM calls "
                    "WHERE run_id=? AND status='reserved'",
                    (run_id,),
                ).fetchall()
            ]

    def cache_get(self, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row["response"]) if row else None

    def cache_put(self, key: str, response: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES(?,?)", (key, json.dumps(response)))

    def artifact(self, run_id: str, kind: str, name: str, content: str) -> dict[str, Any]:
        return self.artifact_bytes(run_id, kind, name, content.encode())

    def artifact_bytes(self, run_id: str, kind: str, name: str, content: bytes) -> dict[str, Any]:
        if name in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("invalid artifact name")
        folder = self.run_dir(run_id) / "artifacts"
        folder.mkdir(mode=0o700, exist_ok=True)
        target = folder / name
        if target.is_symlink() or folder.is_symlink():
            raise ValueError("artifact path is a symlink")
        # Registered paths remain bound to historical bytes even if the file was
        # removed. Do not conceal lost evidence by reusing its original path.
        existing = next(
            (
                a
                for a in self.artifacts(run_id)
                if a["path"] == str(target.relative_to(self.run_dir(run_id)))
            ),
            None,
        )
        if existing and not target.exists():
            raise ValueError("registered artifact is missing; its path cannot be reused")
        if existing:
            current = self.artifact_content(run_id, existing["id"], max_bytes=existing["size"])
            if current == content:
                return existing
            target = folder / f"{uuid.uuid4().hex[:12]}-{name}"
        if target.is_symlink() or folder.is_symlink():
            raise ValueError("artifact path is a symlink")
        temporary = folder / (".artifact-" + uuid.uuid4().hex)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # Atomic replacement also avoids overwriting an external hardlink.
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        record = {
            "id": uuid.uuid4().hex,
            "kind": kind,
            "path": str(target.relative_to(self.run_dir(run_id))),
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        with self.connect() as db:
            db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?)",
                (record["id"], run_id, kind, record["path"], record["sha256"], record["size"]),
            )
        return record

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM artifacts WHERE run_id=?", (run_id,)
                ).fetchall()
            ]

    def artifact_content(
        self, run_id: str, artifact_id: str, *, max_bytes: int = 16 * 1024 * 1024
    ) -> bytes:
        """Read immutable bytes through directory descriptors and verify their receipt."""
        record = next((a for a in self.artifacts(run_id) if a["id"] == artifact_id), None)
        if record is None:
            raise FileNotFoundError("Unknown artifact")
        parts = Path(record["path"]).parts
        if len(parts) != 2 or parts[0] != "artifacts":
            raise ValueError("Invalid artifact path")
        with parent_descriptor(self.run_dir(run_id), record["path"]) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("Artifact must be a regular file")
                if info.st_size > max_bytes:
                    raise ValueError("Artifact exceeds the 16 MiB read limit; inspect it locally")
                content = stream.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("Artifact exceeds the read limit")
        if (
            len(content) != record["size"]
            or hashlib.sha256(content).hexdigest() != record["sha256"]
        ):
            raise ValueError("Artifact integrity check failed")
        return content

    def export_run(self, run_id: str, target: Path, include_private: bool = False) -> None:
        state = self.get_run(run_id)
        # Safe-by-default export is metadata only; redaction cannot guarantee prose privacy.
        result: dict[str, Any] = {
            "id": run_id,
            "stage": state.stage.value,
            "status": state.status,
            "outcome": state.outcome,
            "usage": self.usage(run_id),
            "behavior": state.behavior.model_dump() if state.behavior else None,
            "artifact_hashes": [
                {"kind": a["kind"], "sha256": a["sha256"], "size": a["size"]}
                for a in self.artifacts(run_id)
            ],
        }
        if include_private:
            all_events: list[dict[str, Any]] = []
            while batch := self.events(run_id, all_events[-1]["seq"] if all_events else 0):
                all_events.extend(batch)
            result.update(state=state.model_dump(mode="json"), events=all_events)
            result = redact(result, self.get_config(run_id).privacy.redact_patterns)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(result, indent=2) + "\n")
