"""Persistent repository coding sessions with sandboxed feedback, not one-shot edits.

The tool protocol and operational limits are our reconstruction. Scientific
iteration limits remain in the outer Metis stage machine.
"""

from __future__ import annotations

import difflib
import fnmatch
import hashlib
import json
import os
import shutil
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, ValidationError

from .catalog import load_catalog
from .contracts import AgentOutput, ExperimentResult, ExperimentSpec, FileEdit, Model, RunState
from .errors import BudgetExceeded
from .execution import Executor
from .privacy import redact
from .runtime_support import ExecutionError
from .runtime_support import parent_descriptor as _parent
from .runtime_support import read_text as _read
from .runtime_support import relative_parts as _parts
from .runtime_support import write_file as _write

if TYPE_CHECKING:
    from .config import ResearchConfig
    from .store import Store

CODING_ROLES = {role for role, agent in load_catalog().agents.items() if agent.handler == "coding"}

CODING_PROMPT = load_catalog().prompt("coding_step")


class CodingConfig(Model):
    max_steps: int = Field(default=64, ge=1, le=10000)
    max_commands: int = Field(default=24, ge=1, le=10000)
    wall_seconds: int = Field(default=14400, ge=1)
    command_timeout: int = Field(default=300, ge=1, le=604800)
    max_read_bytes: int = Field(default=200000, ge=1024, le=10000000)
    max_context_chars: int = Field(default=200000, ge=4096)
    max_edit_bytes: int = Field(default=2000000, ge=1024, le=10000000)
    escalation_after_failures: int = Field(default=2, ge=1)


class Replacement(Model):
    path: str
    old_text: str = Field(min_length=1)
    new_text: str


class CodingAction(Model):
    tool: Literal[
        "list", "read", "search", "edit", "delete", "command", "history", "finish", "abort"
    ]
    path: str = ""
    paths: list[str] = Field(default_factory=list)
    edits: list[FileEdit] = Field(default_factory=list)
    replacements: list[Replacement] = Field(default_factory=list)
    argv: list[str] = Field(default_factory=list, max_length=128)
    query: str = ""
    offset: int = Field(default=0, ge=0)
    start_line: int = Field(default=1, ge=1)
    limit: int = Field(default=100, ge=1, le=1000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=604800)
    criterion: str = ""


class CodingFailure(RuntimeError):
    """The task remains scientifically unresolved; all partial work is retained."""


class CodingPending(RuntimeError):
    """A scheduler job is running; resume this stage to collect the same job."""


_EXCLUDED = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_PRIVATE = {".ssh", ".aws", ".azure", ".gnupg", ".kube", ".netrc", "credentials"}


def _safe(relative: str) -> None:
    parts = _parts(relative)
    if any(
        p.lower() in _PRIVATE
        or p.startswith(".env")
        or p.lower().endswith((".pem", ".key", ".p12", ".pfx"))
        for p in parts
    ):
        raise ExecutionError("Coding tools cannot access credential files")


def _files(root: Path) -> list[str]:
    result: list[str] = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs if d not in _EXCLUDED and not d.startswith(".autoresearch-")
        )
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if name.startswith(".autoresearch-") or name == "metrics.json":
                continue
            try:
                _safe(relative)
            except ExecutionError:
                continue
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ExecutionError("Coding workspaces cannot contain symlinks or special files")
            result.append(relative)
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ExecutionError("Coding workspaces cannot contain symlink directories")
    return sorted(result)


def _bytes(root: Path, relative: str, limit: int | None = None) -> bytes:
    _safe(relative)
    with _parent(root, relative) as (fd, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ExecutionError("Coding tools require regular files")
            data = stream.read() if limit is None else stream.read(limit + 1)
    if limit is not None and len(data) > limit:
        raise ExecutionError("File exceeds the configured edit byte limit")
    return data


def _manifest(root: Path) -> dict[str, str]:
    # Hash streams rather than loading an entire large repository into memory.
    result: dict[str, str] = {}
    for relative in _files(root):
        with _parent(root, relative) as (fd, name):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ExecutionError("Coding source changed to a special file")
                digest = hashlib.sha256()
                while chunk := stream.read(1048576):
                    digest.update(chunk)
        result[relative] = digest.hexdigest()
    return result


def _copy(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ExecutionError("Coding source must be a real directory")
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    for relative in _files(source):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _parent(source, relative) as (fd, name):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(descriptor, "rb") as stream, destination.open("xb") as output:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ExecutionError("Coding source changed to a special file")
                shutil.copyfileobj(stream, output)
        destination.chmod(0o600)


def _fingerprint(manifest: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


class CodingSession:
    def __init__(
        self,
        state: RunState,
        call: Callable[[str, dict[str, Any]], AgentOutput],
        store: Store,
        config: ResearchConfig,
        context: dict[str, Any],
    ) -> None:
        self.state, self.call, self.store, self.config = state, call, store, config
        self.settings = config.coding
        self.context = dict(context)
        source = Path(context.get("source_dir", store.run_dir(state.id) / "source"))
        # The source path is supplied by the orchestrator, never the model's actions.
        identity = {
            "stage": str(state.stage),
            "role": context.get("original_role", str(state.stage)),
            "round": state.round,
            "idea": state.current_idea,
            "selected": state.selected_idea,
            "plan_index": state.plan_index,
            "counters": state.counters,
            "experiments": [e.id for e in state.experiments],
            "feedback": state.feedback,
            "catalog_digest": context.get("catalog_digest", "legacy"),
            "role_instruction": context.get("role_instruction", ""),
        }
        self.id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        self.folder = store.run_dir(state.id) / "coding" / self.id
        self.root = self.folder / "workspace"
        self.original = self.folder / "original"
        self.checkpoint_path = self.folder / "checkpoint.json"
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.folder.is_symlink():
            raise ExecutionError("Coding session path must not be a symlink")
        if self.checkpoint_path.exists():
            self.record = json.loads(_read(self.folder, "checkpoint.json", 64000000))
            if self.record.get("schema_version") != 1:
                raise CodingFailure("Unsupported coding checkpoint schema version")
        else:
            # Creation interrupted before its first checkpoint has no executed work.
            for path in (self.root, self.original):
                if path.exists():
                    shutil.rmtree(path)
            _copy(source, self.original)
            _copy(self.original, self.root)
            self.record = {
                "schema_version": 1,
                "id": self.id,
                "identity": identity,
                "created_at": time.time(),
                "steps": [],
                "commands": 0,
                "pending": None,
                "completed": None,
                "last_success_code": None,
                "consecutive_failures": 0,
                "initial_manifest": _manifest(self.original),
            }
            self.save()
        self.executor = Executor(config.execution)

    def save(self) -> None:
        _write(self.folder, "checkpoint.json", json.dumps(self.record, ensure_ascii=False))

    def protected(self, relative: str) -> bool:
        return any(
            fnmatch.fnmatch(relative, pattern) for pattern in self.config.project.protected_paths
        )

    def ensure_editable(self, relative: str) -> None:
        _safe(relative)
        if self.protected(relative):
            raise ExecutionError("Cannot edit or delete a protected evaluator/specification")
        if relative == "metrics.json":
            raise ExecutionError("Metrics are generated observations, not editable source")

    def observation(self, action: CodingAction) -> dict[str, Any]:
        if action.tool == "history":
            history = self.record["steps"]
            return {
                "steps": history[action.offset : action.offset + action.limit],
                "total": len(history),
            }
        if action.tool in {"list", "search"}:
            if action.path:
                _safe(action.path)
            files = [
                p
                for p in _files(self.root)
                if not action.path
                or p == action.path
                or p.startswith(action.path.rstrip("/") + "/")
            ]
            if action.tool == "list":
                return {
                    "files": files[action.offset : action.offset + action.limit],
                    "total": len(files),
                    "next_offset": action.offset + action.limit
                    if len(files) > action.offset + action.limit
                    else None,
                }
            if not action.query:
                raise ExecutionError("Search requires a nonempty literal query")
            matches: list[dict[str, Any]] = []
            skipped_large: list[str] = []
            for relative in files:
                # Search line by line, bounded by file size; offer explicit targeted reads.
                if (self.root / relative).stat().st_size > 10000000:
                    skipped_large.append(relative)
                    continue
                text = _read(self.root, relative, 10000000)
                if "\x00" in text:
                    continue
                for number, line in enumerate(text.splitlines(), 1):
                    if action.query in line:
                        matches.append({"path": relative, "line": number, "text": line[:2000]})
            return {
                "matches": matches[action.offset : action.offset + action.limit],
                "total": len(matches),
                "skipped_large_files": skipped_large,
                "next_offset": action.offset + action.limit
                if len(matches) > action.offset + action.limit
                else None,
            }
        if action.tool == "read":
            _safe(action.path)
            # Use a streaming line scan so late portions of large files are reachable.
            lines: list[str] = []
            used, total, truncated = 0, 0, False
            with _parent(self.root, action.path) as (fd, name):
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                with os.fdopen(descriptor, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ExecutionError("Read requires a regular file")
                    # readline's bound prevents an adversarial unbroken line consuming memory.
                    while raw := stream.readline(self.settings.max_read_bytes + 1):
                        total += 1
                        if total < action.start_line:
                            continue
                        if (
                            len(lines) >= action.limit
                            or used + len(raw) > self.settings.max_read_bytes
                        ):
                            truncated = True
                            break
                        if b"\x00" in raw:
                            raise ExecutionError(
                                "Binary data requires a sandboxed inspection command"
                            )
                        used += len(raw)
                        lines.append(raw.decode("utf-8", errors="replace"))
            return {
                "path": action.path,
                "start_line": action.start_line,
                "text": "".join(lines),
                "truncated": truncated,
                "next_line": action.start_line + len(lines) if truncated and lines else None,
            }
        if action.tool == "edit":
            pending: dict[str, str] = {}
            for edit in action.edits:
                if edit.path in pending:
                    raise ExecutionError("Duplicate edit path in one transaction")
                self.ensure_editable(edit.path)
                pending[edit.path] = edit.content
            for replacement in action.replacements:
                self.ensure_editable(replacement.path)
                original_text = pending.get(replacement.path)
                if original_text is None:
                    original_text = _bytes(
                        self.root, replacement.path, self.settings.max_edit_bytes
                    ).decode("utf-8")
                if original_text.count(replacement.old_text) != 1:
                    raise ExecutionError(
                        "Replacement old_text must match exactly once; inspect the file again"
                    )
                pending[replacement.path] = original_text.replace(
                    replacement.old_text, replacement.new_text, 1
                )
            if not pending:
                raise ExecutionError("Edit requires files or exact replacements")
            for relative, text in pending.items():
                if len(text.encode()) > self.settings.max_edit_bytes:
                    raise ExecutionError("Edit exceeds configured maximum bytes")
                # Preflight all parents/files before applying the multi-file batch.
                with _parent(self.root, relative, create=True) as (fd, name):
                    try:
                        mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
                    except FileNotFoundError:
                        continue
                    if not stat.S_ISREG(mode):
                        raise ExecutionError("Cannot overwrite a symlink or special file")
            for relative, text in pending.items():
                _write(self.root, relative, text)
            return {"edited": list(pending)}
        if action.tool == "delete":
            for relative in action.paths:
                self.ensure_editable(relative)
                with _parent(self.root, relative) as (fd, name):
                    if not stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                        raise ExecutionError("Can only delete regular files")
            for relative in action.paths:
                with _parent(self.root, relative) as (fd, name):
                    os.unlink(name, dir_fd=fd)
            return {"deleted": action.paths}
        raise ExecutionError("Action must be dispatched by the session controller")

    def _diff(self, before: dict[str, str], after: dict[str, str], step: int) -> dict[str, Any]:
        changed = [p for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
        # Versioned full source snapshots live outside the workload's mounted root.
        chunks: list[str] = []
        snapshots: list[dict[str, Any]] = []
        for relative in changed:
            old_path = self.folder / "versions" / relative
            old = (
                _read(self.folder / "versions", relative, self.settings.max_edit_bytes)
                if old_path.exists()
                else ""
            )
            new = (
                _read(self.root, relative, self.settings.max_edit_bytes)
                if relative in after
                else ""
            )
            chunks.extend(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                )
            )
            if relative in after:
                if (self.root / relative).stat().st_size > self.settings.max_edit_bytes:
                    snapshots.append(
                        {
                            "path": relative,
                            "sha256": after[relative],
                            "content_omitted": "exceeds edit byte limit",
                        }
                    )
                else:
                    data = _bytes(self.root, relative)
                    _write(self.folder / "versions", relative, data)
                    # A separate step tree preserves every changed file, including failed attempts.
                    tree = self.folder / "snapshots" / str(step)
                    tree.mkdir(parents=True, exist_ok=True, mode=0o700)
                    _write(tree, relative, data)
                    snapshots.append(
                        {
                            "path": relative,
                            "sha256": after[relative],
                            "snapshot": str((tree / relative).relative_to(self.folder)),
                        }
                    )
            elif old_path.exists():
                old_path.unlink()
        artifact = self.store.artifact(
            self.state.id, "coding_diff", f"coding-{self.id}-{step}.diff", "".join(chunks)
        )
        return {"changed_paths": changed, "diff_artifact": artifact, "snapshots": snapshots}

    def command(self, action: CodingAction, step: int) -> dict[str, Any]:
        if not action.argv:
            raise ExecutionError("Command requires a nonempty argv")
        pending = self.record["pending"]
        receipt_name = f"command-{step}.json"
        receipt = self.folder / receipt_name
        if receipt.exists():
            result = ExperimentResult.model_validate_json(
                _read(self.folder, receipt_name, 64000000)
            )
        else:
            spec = ExperimentSpec(
                id=f"coding-{self.id}-{step}",
                kind="coding_check",
                workspace=str(self.root),
                argv=action.argv,
                timeout_seconds=min(
                    action.timeout_seconds or self.settings.command_timeout,
                    self.settings.command_timeout,
                ),
                seed=self.config.project.seeds[0],
                metadata={
                    "protected_files": [p for p in _files(self.original) if self.protected(p)],
                    "dataset_manifest": self.config.project.dataset_manifest,
                },
            )
            if pending.get("job_id"):
                result = self.executor.poll(spec, pending["job_id"])
            elif (
                pending.get("started")
                and self.config.execution.backend == "slurm"
                and (self.root / ".autoresearch-execution.json").exists()
            ):
                # Recover the scheduler's durable submission receipt even if the
                # controller died before copying its job id into this checkpoint.
                result = self.executor.run(spec, command_only=True)
            elif pending.get("started"):
                # The process may have completed just before a crash. Blind replay could
                # duplicate expensive work, so expose the uncertainty to the coding agent.
                result = ExperimentResult(
                    id=spec.id,
                    status="failed",
                    stderr="Interrupted command has no durable receipt; execution outcome is unknown. Inspect files/logs before deciding to rerun.",
                    provenance={"uncertain_execution": True, "argv": spec.argv},
                )
            else:
                if self.record["commands"] >= self.settings.max_commands:
                    raise self.budget_failure("Coding command budget exhausted")
                pending["started"] = True
                self.record["commands"] += 1
                self.save()
                result = self.executor.run(spec, command_only=True)
            if result.status == "pending":
                pending["job_id"] = result.job_id
                self.save()
                raise CodingPending(f"Coding command is running as scheduler job {result.job_id}")
            # Local/Slurm are trusted execution modes. Detect and restore any protocol
            # corruption. Docker additionally mounts these files read-only.
            violations: list[str] = []
            for relative in _files(self.original):
                if not self.protected(relative):
                    continue
                original = _bytes(self.original, relative)
                try:
                    changed = _bytes(self.root, relative) != original
                except (OSError, ExecutionError):
                    changed = True
                if changed:
                    violations.append(relative)
                    _write(self.root, relative, original)
            if violations:
                result.status = "failed"
                result.metrics = {}
                result.stderr += "\nProtected source modification detected: " + ", ".join(
                    violations
                )
                result.provenance["protected_modifications"] = violations
            _write(self.folder, receipt_name, result.model_dump_json())
        # Retire the completed scheduler receipt only after saving our durable result;
        # the next command uses the same workspace but has a distinct scheduler job.
        if self.config.execution.backend == "slurm":
            (self.root / ".autoresearch-execution.json").unlink(missing_ok=True)
        artifact = self.store.artifact(
            self.state.id,
            "coding_command",
            f"coding-{self.id}-{step}.json",
            json.dumps(redact(result.model_dump(mode="json")), indent=2),
        )
        return {
            "result": result.model_dump(mode="json"),
            "artifact": artifact,
            "counts_as_formal_experiment": False,
        }

    def _context(self) -> dict[str, Any]:
        steps = self.record["steps"]
        # Complete history stays addressable; context compaction is explicit, not loss.
        recent: list[dict[str, Any]] = []
        used = 0
        for item in reversed(steps):
            size = len(json.dumps(item))
            if used + size > self.settings.max_context_chars // 2 and recent:
                break
            recent.insert(0, item)
            used += size
        return {
            **{k: v for k, v in self.context.items() if k not in {"source_files", "source_dir"}},
            "coding_session": self.id,
            "tool_protocol": self.context.get("tool_protocol", CODING_PROMPT),
            "steps_completed": len(steps),
            "steps_remaining": self.settings.max_steps - len(steps),
            "commands_remaining": self.settings.max_commands - self.record["commands"],
            "protected_paths": self.config.project.protected_paths,
            "allowed_executables": self.config.execution.allowed_executables,
            "recent_steps": recent,
            "omitted_steps": len(steps) - len(recent),
            "history_access": self.context.get(
                "history_access", load_catalog().text("prompts/history.md")
            ),
            "escalate": self.record["consecutive_failures"]
            >= self.settings.escalation_after_failures,
            "escalation_reason": "repeated executable-check/tool failures"
            if self.record["consecutive_failures"] >= self.settings.escalation_after_failures
            else "",
        }

    def finish(self, action: CodingAction, output: AgentOutput) -> AgentOutput:
        current = _manifest(self.root)
        if not action.criterion.strip():
            raise ExecutionError("Finish requires an explicit validation criterion")
        if self.record["last_success_code"] != _fingerprint(current):
            raise ExecutionError(
                "Run a meaningful successful check after the latest code edits before finishing"
            )
        if not output.argv:
            raise ExecutionError("Finish must supply reproducible final experiment argv")
        probe = ExperimentSpec(
            id="validate-final", kind="coding", workspace=str(self.root), argv=output.argv
        )
        self.executor._validate(probe)
        edits: list[FileEdit] = []
        initial = self.record["initial_manifest"]
        declared_new = set(action.paths)
        for relative in action.paths:
            self.ensure_editable(relative)
            if relative not in current:
                raise ExecutionError(
                    "Declared source export does not exist in the checked workspace"
                )
        for entry in self.record["steps"]:
            previous = entry.get("action", {})
            if isinstance(previous, dict) and previous.get("tool") == "edit":
                # Successful edit observations cover full writes and replacements.
                # A refused/protected edit stays in history but cannot poison finish.
                declared_new.update(entry.get("observation", {}).get("edited", []))
        for relative in declared_new:
            self.ensure_editable(relative)
        for path, digest in current.items():
            if path not in initial and path not in declared_new:
                continue
            if digest != initial.get(path):
                self.ensure_editable(path)
                try:
                    content = _bytes(self.root, path, self.settings.max_edit_bytes).decode("utf-8")
                except UnicodeDecodeError:
                    raise ExecutionError(
                        "Changed binary source cannot be exported as a text edit; generate it reproducibly from the final command"
                    ) from None
                edits.append(FileEdit(path=path, content=content))
        deleted = sorted(set(initial) - set(current))
        for path in deleted:
            self.ensure_editable(path)
        output.files = edits
        output.deleted_files = deleted
        output.plans = [
            {
                "coding_session": self.id,
                "criterion": action.criterion,
                "commands": self.record["commands"],
                "steps": len(self.record["steps"]),
                "scientific_criterion_pending": True,
            }
        ]
        output.feedback += "\nCoding checks completed; independent formal experiment and scientific critique remain required."
        self.record["completed"] = output.model_dump(mode="json")
        self.save()
        return output

    def budget_failure(self, reason: str) -> CodingFailure:
        """Summarize preserved evidence without replaying commands or exposing raw paths."""
        message = (
            f"{reason}; partial work retained. "
            f"{len(self.record['steps'])}/{self.settings.max_steps} steps, "
            f"{self.record['commands']}/{self.settings.max_commands} commands. "
            f"Checkpoint relative to run directory: coding/{self.id}/checkpoint.json."
        )
        for entry in reversed(self.record["steps"]):
            observation = entry["observation"]
            result = observation.get("result", {})
            detail = observation.get("error")
            if not detail and result.get("status") in {"failed", "timeout", "cancelled"}:
                detail = f"{result['status']}, exit code {result.get('exit_code')}"
                output = result.get("stderr") or result.get("stdout") or ""
                # Redact before truncation so a split credential cannot escape masking.
                output = str(redact(output, self.config.privacy.redact_patterns))
                detail += ": " + " ".join(output.split())[-600:]
            if detail:
                action = entry.get("action")
                tool = (
                    action.get("tool", "invalid action")
                    if isinstance(action, dict)
                    else "invalid action"
                )
                detail = str(redact(str(detail), self.config.privacy.redact_patterns))
                message += (
                    f" Last recorded failure: step {entry['step'] + 1}, {tool}: "
                    + " ".join(detail.split())[:700]
                    + ". Earlier failures may have been repaired; inspect the checkpoint before recovery."
                )
                break
        return CodingFailure(message)

    def run(self) -> AgentOutput:
        if self.record["completed"]:
            return AgentOutput.model_validate(self.record["completed"])
        versions = self.folder / "versions"
        if not versions.exists():
            _copy(self.original, versions)
        while len(self.record["steps"]) < self.settings.max_steps:
            if self.store.is_paused(self.state.id):
                raise CodingPending("Coding session paused by operator")
            if time.time() - self.record["created_at"] > self.settings.wall_seconds:
                raise self.budget_failure("Coding wall-clock budget exhausted")
            step = len(self.record["steps"])
            pending = self.record["pending"]
            if pending is None:
                output = self.call("coding_step", self._context())
                pending = {
                    "output": output.model_dump(mode="json"),
                    "started": False,
                    "before_manifest": _manifest(self.root),
                }
                self.record["pending"] = pending
                self.save()
            else:
                output = AgentOutput.model_validate(pending["output"])
            before = pending.get("before_manifest", _manifest(self.root))
            action: CodingAction | None = None
            try:
                if len(output.plans) != 1:
                    raise ExecutionError("Return exactly one tool action in plans")
                action = CodingAction.model_validate(output.plans[0])
                if action.tool == "finish":
                    return self.finish(action, output)
                if action.tool == "abort":
                    raise CodingFailure(action.criterion or output.summary)
                observation = (
                    self.command(action, step)
                    if action.tool == "command"
                    else self.observation(action)
                )
                failed = action.tool == "command" and observation["result"]["status"] != "completed"
                if action.tool == "command":
                    self.record["last_success_code"] = (
                        None if failed else _fingerprint(_manifest(self.root))
                    )
                self.record["consecutive_failures"] = (
                    self.record["consecutive_failures"] + 1
                    if failed
                    else 0
                    if action.tool == "command"
                    else self.record["consecutive_failures"]
                )
            except (CodingPending, CodingFailure, BudgetExceeded):
                raise
            except (ExecutionError, OSError, ValueError, ValidationError) as error:
                observation = {"error": str(redact(str(error)))}
                self.record["consecutive_failures"] += 1
                if action and action.tool == "command":
                    self.record["last_success_code"] = None
            after = _manifest(self.root)
            entry = {
                "step": step,
                "action": action.model_dump() if action else output.plans,
                "summary": output.summary,
                "observation": observation,
                "before_sha256": _fingerprint(before),
                "after_sha256": _fingerprint(after),
                **self._diff(before, after, step),
            }
            self.record["steps"].append(entry)
            self.record["pending"] = None
            self.save()
            self.store.event(
                self.state.id, "coding_step", str(self.state.stage), {"session": self.id, **entry}
            )
        raise self.budget_failure("Coding step budget exhausted")


def run_coding(
    state: RunState,
    call: Callable[[str, dict[str, Any]], AgentOutput],
    store: Store,
    config: ResearchConfig,
    context: dict[str, Any],
) -> AgentOutput:
    """Iterate on tests/pilots, then export source changes for the formal experiment."""
    return CodingSession(state, call, store, config, context).run()
