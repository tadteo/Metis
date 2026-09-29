"""Private SQLite journal, atomic checkpoints, leases and budget reservations."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ResearchConfig
from .contracts import RunState, Usage
from .errors import BudgetExceeded as BudgetExceeded
from .privacy import redact


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
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, state TEXT NOT NULL, config TEXT NOT NULL, version INTEGER NOT NULL, paused INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, timestamp TEXT NOT NULL, kind TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_run ON events(run_id,seq);
                CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL, reserved REAL NOT NULL, usage TEXT NOT NULL, request_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, response TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS leases(run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, pid INTEGER NOT NULL, host TEXT NOT NULL);
            """)
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

    def reserve(
        self, run_id: str, role: str, maximum: float, request_hash: str, *, idempotent: bool = False
    ) -> str:
        if isinstance(maximum, bool) or not math.isfinite(maximum) or maximum < 0:
            raise ValueError("budget reservation must be finite and nonnegative")
        config = self.get_config(run_id)
        call_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if idempotent:
                existing = db.execute(
                    "SELECT id,reserved FROM calls WHERE run_id=? AND role=? AND request_hash=?",
                    (run_id, role, request_hash),
                ).fetchone()
                if existing is not None:
                    if existing["reserved"] != maximum:
                        raise ConflictError("idempotent reservation amount changed")
                    return str(existing["id"])
            rows = db.execute(
                "SELECT status,reserved,usage,role FROM calls WHERE run_id=?", (run_id,)
            ).fetchall()
            spent = sum(float(json.loads(r["usage"]).get("cost_usd", 0)) for r in rows)
            held = sum(r["reserved"] for r in rows if r["status"] == "reserved")
            child_events = db.execute(
                "SELECT payload FROM events WHERE run_id=? AND kind='paper_orchestra_api_call'",
                (run_id,),
            ).fetchall()
            child_ids = {
                json.loads(row["payload"]).get("id", str(index))
                for index, row in enumerate(child_events)
            }
            attempted_calls = sum(row["role"] != "paper_orchestra" for row in rows) + len(child_ids)
            if (
                spent + held + maximum > config.budget.usd
                or attempted_calls >= config.budget.max_calls
            ):
                raise BudgetExceeded(
                    "model budget reached; raise budget explicitly before resuming"
                )
            db.execute(
                "INSERT INTO calls VALUES(?,?,?,?,?,?,?)",
                (call_id, run_id, role, "reserved", maximum, "{}", request_hash),
            )
        return call_id

    def call_for_request(self, run_id: str, role: str, request_hash: str) -> dict[str, Any] | None:
        """Read a durable idempotent reservation without exposing raw database ownership."""
        with self.connect() as db:
            row = db.execute(
                "SELECT id,status,reserved,usage FROM calls WHERE run_id=? AND role=? AND request_hash=?",
                (run_id, role, request_hash),
            ).fetchone()
        return dict(row) if row is not None else None

    def settle(self, call_id: str, usage: Usage) -> None:
        # Revalidate extension-provided models, including objects created with
        # model_construct. Settled costs are an append-only accounting fact.
        usage = Usage.model_validate(usage.model_dump())
        encoded = usage.model_dump_json()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status,reserved,usage FROM calls WHERE id=?", (call_id,)
            ).fetchone()
            if row is None:
                raise KeyError("budget reservation not found")
            if row["status"] == "settled":
                if json.loads(row["usage"]) != usage.model_dump():
                    raise ConflictError("a settled model call cannot be overwritten")
                return
            db.execute("UPDATE calls SET status='settled',usage=? WHERE id=?", (encoded, call_id))
            overspent = usage.cost_usd > row["reserved"] + 1e-9
        if overspent:
            # Commit the actual bill before stopping. Raising inside the
            # transaction would incorrectly erase an already-incurred charge.
            raise BudgetExceeded(
                "reported model cost exceeded its reservation; actual usage was recorded"
            )

    def usage(self, run_id: str) -> dict[str, Any]:
        config = self.get_config(run_id)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM calls WHERE run_id=?", (run_id,)).fetchall()
        result: dict[str, Any] = {
            "cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": len(rows),
            "reserved_usd": 0.0,
            "budget_usd": config.budget.usd,
        }
        for row in rows:
            usage = json.loads(row["usage"])
            for key in ("cost_usd", "input_tokens", "output_tokens"):
                result[key] += usage.get(key, 0)
            if row["status"] == "reserved":
                result["reserved_usd"] += row["reserved"]
        with self.connect() as db:
            child_rows = db.execute(
                "SELECT payload FROM events WHERE run_id=? AND kind='paper_orchestra_api_call'",
                (run_id,),
            ).fetchall()
        children = {
            json.loads(row["payload"]).get("id", str(index)): json.loads(row["payload"])
            for index, row in enumerate(child_rows)
        }
        writer_jobs = sum(row["role"] == "paper_orchestra" for row in rows)
        result["subordinate_calls"] = len(children)
        result["model_calls_attempted"] = len(rows) - writer_jobs + len(children)
        result["writer_jobs"] = writer_jobs
        # Token/cost sums are already settled by the parent reservation; do not double bill.
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
        if target.exists():
            current = target.read_bytes()
            if existing and hashlib.sha256(current).hexdigest() != existing["sha256"]:
                raise ValueError("registered artifact content failed its integrity check")
            if current == content and existing:
                return existing
            if existing:
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

    def artifact_content(
        self, run_id: str, artifact_id: str, *, max_bytes: int = 16 * 1024 * 1024
    ) -> bytes:
        record = next((a for a in self.artifacts(run_id) if a["id"] == artifact_id), None)
        if record is None:
            raise FileNotFoundError("Unknown artifact")
        root = self.run_dir(run_id)
        folder = root / "artifacts"
        target = root / record["path"]
        if folder.is_symlink() or target.parent != folder or target.is_symlink():
            raise ValueError("Artifact path is not inside this run's artifact directory")
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            content = stream.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("Artifact exceeds the browser download limit; inspect it locally")
        if (
            len(content) != record["size"]
            or hashlib.sha256(content).hexdigest() != record["sha256"]
        ):
            raise ValueError("Registered artifact content failed its integrity check")
        return content

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM artifacts WHERE run_id=?", (run_id,)
                ).fetchall()
            ]

    def export_run(self, run_id: str, target: Path, include_private: bool = False) -> None:
        state = self.get_run(run_id)
        # Safe-by-default export is metadata only; redaction cannot guarantee prose privacy.
        result: dict[str, Any] = {
            "id": run_id,
            "stage": state.stage.value,
            "status": state.status,
            "outcome": state.outcome,
            "usage": self.usage(run_id),
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
