"""Isolated argv execution and resumable Slurm jobs in private experiment workspaces.

Local execution is deliberately opt-in: an executable allowlist is not a sandbox
for generated Python. Docker is the default security boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .contracts import ExecutionConfig, ExperimentResult, ExperimentSpec
from .privacy import redact
from .providers import strict_json
from .runtime_support import ExecutionError as ExecutionError
from .runtime_support import ProcessResult as _Process
from .runtime_support import content_digest as _digest
from .runtime_support import copy_file, file_identity, program_source
from .runtime_support import parent_descriptor as _parent
from .runtime_support import read_text as _read
from .runtime_support import relative_parts as _parts
from .runtime_support import run_process as _run
from .runtime_support import write_file as _write

# Compatibility exports for existing integrations; new callers use runtime_support.
__all__ = [
    "ExecutionError",
    "Executor",
    "_Process",
    "_digest",
    "_parent",
    "_parts",
    "_read",
    "_run",
    "_write",
]

_PREFIX = ".autoresearch-"
_META = _PREFIX + "execution.json"
_STDOUT = _PREFIX + "stdout.log"
_STDERR = _PREFIX + "stderr.log"
_SHELLS = {"sh", "bash", "zsh", "dash", "fish", "csh", "cmd", "powershell", "pwsh", "env"}
_SENSITIVE_NAMES = {
    ".ssh",
    ".aws",
    ".azure",
    ".gnupg",
    ".kube",
    ".docker",
    ".config",
    ".codex",
    ".netrc",
    ".git-credentials",
    "credentials",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
}
_CODE_SUFFIXES = {
    ".py",
    ".pyi",
    ".sh",
    ".r",
    ".jl",
    ".cpp",
    ".c",
    ".h",
    ".rs",
    ".go",
    ".ipynb",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".cfg",
    ".ini",
    ".lock",
}


def _workspace(spec: ExperimentSpec) -> Path:
    path = Path(spec.workspace)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise ExecutionError("Experiment workspace must be an existing absolute directory")
    return path.resolve(strict=True)


def _code_hash(root: Path, spec: ExperimentSpec) -> str:
    digest = hashlib.sha256()
    edited = {edit.path for edit in spec.files}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {".git", ".venv", "__pycache__"})
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if name.startswith(_PREFIX) or relative == spec.metrics_file:
                continue
            if path.suffix.lower() not in _CODE_SUFFIXES and relative not in edited:
                continue
            with _parent(root, relative) as (descriptor, leaf):
                fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                with os.fdopen(fd, "rb") as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise ExecutionError("Source code must contain only regular files")
                    digest.update(relative.encode() + b"\x00")
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
                    digest.update(b"\x00")
    return digest.hexdigest()


# This trusted wrapper drains both streams while saving bounded logs on the
# compute node. Its JSON input is data; model text never becomes shell syntax.
_SLURM_RUNNER = program_source("slurm_runner")


class Executor:
    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config.model_copy(deep=True)
        for value in (config.slurm_partition, config.slurm_account):
            if value and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value):
                raise ExecutionError("Invalid Slurm partition or account")
        for name in config.allowed_executables:
            if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", name) or name in _SHELLS:
                raise ExecutionError(
                    "Allowed executables must be bare program names, excluding shells"
                )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]*", config.docker_image):
            raise ExecutionError("Invalid Docker image reference")

    def _validate(self, spec: ExperimentSpec) -> Path:
        root = _workspace(spec)
        if self.config.backend == "docker" and "," in str(root):
            raise ExecutionError("Docker workspace paths cannot contain commas")
        if self.config.backend == "local" and not self.config.allow_local:
            raise ExecutionError("Local execution requires execution.allow_local=true")
        if spec.argv[0] not in self.config.allowed_executables:
            raise ExecutionError("Experiment executable is not explicitly allowed")
        if any("\x00" in part or len(part) > 131072 for part in spec.argv):
            raise ExecutionError("Invalid or oversized command argument")
        _parts(spec.metrics_file)
        for edit in spec.files:
            _parts(edit.path)
            if len(edit.content.encode()) > 10 * 1024 * 1024:
                raise ExecutionError("Experiment file edit exceeds 10 MiB")
        evaluator = spec.metadata.get("evaluator_argv", [])
        protected = spec.metadata.get("protected_files", [])
        if (
            not isinstance(evaluator, list)
            or not isinstance(protected, list)
            or any(not isinstance(part, str) or "\x00" in part for part in evaluator)
            or any(not isinstance(part, str) for part in protected)
        ):
            raise ExecutionError("Invalid operator evaluator configuration")
        for relative in protected:
            _parts(relative)
        if any(edit.path in protected for edit in spec.files):
            raise ExecutionError("Model edits cannot modify protected evaluator files")
        if evaluator:
            if evaluator[0] not in self.config.allowed_executables:
                raise ExecutionError("Evaluator executable is not explicitly allowed")
            if not any(argument in protected for argument in evaluator[1:]):
                raise ExecutionError(
                    "Evaluator argv must reference a protected relative script path"
                )
        analyses = spec.metadata.get("analysis_artifacts", [])
        if not isinstance(analyses, list) or any(not isinstance(path, str) for path in analyses):
            raise ExecutionError("Invalid registered analysis artifact paths")
        if analyses and not evaluator:
            raise ExecutionError("Registered statistical analyses require a protected evaluator")
        for path in analyses:
            _parts(path)
            if path == spec.metrics_file or path in protected:
                raise ExecutionError("Analysis artifacts cannot replace metrics or protected files")
        return root

    def _env(self, spec: ExperimentSpec) -> dict[str, str]:
        return {
            "PATH": os.defpath,
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": str(spec.seed % (2**32)),
            "AUTORESEARCH_SEED": str(spec.seed),
            "AUTORESEARCH_EXPERIMENT_KIND": spec.kind,
            "PYTHONUNBUFFERED": "1",
            # Rapid same-size repairs otherwise reuse timestamp-based .pyc files.
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def validate_datasets(self) -> None:
        """Inspect configured data without running a command or creating a workspace."""
        self._data_mounts(None)

    def _data_mounts(self, root: Path | None) -> list[dict[str, str]]:
        """Validate explicit dataset directories without hashing large contents.

        Name checks are defense in depth; operators remain responsible for
        selecting dataset directories that contain no credentials or secrets.
        """
        mounts: list[dict[str, str]] = []
        sources: list[Path] = []
        targets: set[str] = set()
        home = Path.home().resolve()

        def sensitive(name: str) -> bool:
            lower = name.lower()
            return (
                lower in _SENSITIVE_NAMES
                or lower.startswith(".env")
                or lower.endswith((".pem", ".p12", ".pfx", ".key"))
            )

        def unreadable(_: OSError) -> None:
            raise ExecutionError("Dataset mount contains an inaccessible directory")

        for source_text, target in self.config.readonly_mounts.items():
            source = Path(source_text)
            if (
                not source.is_absolute()
                or not source.is_dir()
                or "," in source_text
                or source.resolve() != source
                or not re.fullmatch(r"/data/[A-Za-z0-9][A-Za-z0-9_.-]*", target)
                or target in targets
            ):
                raise ExecutionError(
                    "Dataset mounts require existing nonsymlink absolute directories and unique /data/<name> targets"
                )
            if (
                source == Path("/")
                or home.is_relative_to(source)
                or any(
                    source.is_relative_to(Path(path))
                    for path in (
                        "/etc",
                        "/private/etc",
                        "/proc",
                        "/sys",
                        "/dev",
                        "/run",
                        "/var/run",
                        "/private/var/run",
                    )
                )
                or any(sensitive(part) for part in source.parts)
                or (root is not None and root.is_relative_to(source))
                or (root is not None and source.is_relative_to(root))
                or any(source.is_relative_to(old) or old.is_relative_to(source) for old in sources)
            ):
                raise ExecutionError(
                    "Dataset mount exposes a protected path or overlaps another workspace/mount"
                )
            for directory, dirs, files in os.walk(source, followlinks=False, onerror=unreadable):
                for name in [*dirs, *files]:
                    child = Path(directory) / name
                    if sensitive(name) or child.is_symlink():
                        raise ExecutionError("Dataset mount contains a credential path or symlink")
                    mode = child.stat().st_mode
                    if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
                        raise ExecutionError("Dataset mount must contain only ordinary data files")
            sources.append(source)
            targets.add(target)
            mounts.append({"source": str(source), "target": target})
        return mounts

    def _tool(self, name: str) -> str:
        found = shutil.which(name)
        if not found:
            raise ExecutionError(f"Execution tool is unavailable: {name}")
        return found

    def _provenance(self, root: Path, spec: ExperimentSpec) -> dict[str, Any]:
        mounts = self._data_mounts(root)
        manifest = spec.metadata.get("dataset_manifest", {})
        verified: dict[str, str] = {}
        unverified: list[str] = []
        if not isinstance(manifest, dict):
            raise ExecutionError("Dataset manifest must be a mapping")
        for entry, expected in manifest.items():
            if not isinstance(entry, str) or not entry.startswith("sha256:"):
                unverified.append(str(entry))
                continue
            if not isinstance(expected, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
                raise ExecutionError(
                    "Explicit dataset SHA-256 entries require a 64-digit hex digest"
                )
            relative = entry.removeprefix("sha256:")
            source = root
            if relative.startswith("/"):
                matched = next((m for m in mounts if relative.startswith(m["target"] + "/")), None)
                if matched is None:
                    raise ExecutionError("Dataset digest path must name a configured /data mount")
                source = Path(matched["source"])
                relative = relative[len(matched["target"]) + 1 :]
            _parts(relative)
            digest = hashlib.sha256()
            with _parent(source, relative) as (descriptor, name):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                with os.fdopen(fd, "rb") as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise ExecutionError("Dataset digest target must be a regular file")
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
            actual = digest.hexdigest()
            if actual != expected.lower():
                raise ExecutionError(f"Dataset SHA-256 mismatch for {entry}")
            verified[entry] = actual
        environment: dict[str, Any] = {
            "backend": self.config.backend,
            "env": self._env(spec),
            "cpus": self.config.cpus,
            "memory_mb": self.config.memory_mb,
            "gpus": self.config.gpus,
            "readonly_mounts": mounts,
        }
        if self.config.backend == "docker":
            environment["image"] = self.config.docker_image
        elif self.config.backend == "local":
            environment["python"] = sys.version
        from .planned_statistics import register_plan

        registration = register_plan(root) if spec.metadata.get("analysis_artifacts") else None
        if (
            "registered_statistical_plan" in spec.metadata
            and registration != spec.metadata["registered_statistical_plan"]
        ):
            raise ExecutionError(
                "Reproduction statistical plan differs from its original registration"
            )
        return {
            "registered_statistical_plan": registration,
            "backend": self.config.backend,
            # Exact argv is needed for private checkpoint reproduction. Public
            # event/export boundaries apply privacy.redact to this provenance.
            "argv": spec.argv,
            "workspace": str(root),
            "metric_units": spec.metadata.get("metric_units", {}),
            "analysis_artifacts": spec.metadata.get("analysis_artifacts", []),
            "analysis_inputs": spec.metadata.get("analysis_inputs", []),
            "seed": spec.seed,
            "code_sha256": _code_hash(root, spec),
            "command_sha256": _digest(spec.argv),
            "environment_sha256": _digest(environment),
            "environment": environment,
            "data_provenance": {
                "readonly_mounts": mounts,
                "mounts_applied": self.config.backend == "docker",
                "operator_manifest": manifest,
                "manifest_verified": bool(verified) and not unverified,
                "file_manifest_verified": bool(verified),
                "verified_sha256": verified,
                "unverified_manifest_entries": unverified,
                "verification_scope": "Declared file contents before execution; metadata claims and later dataset changes are not certified",
            },
            "spec_sha256": _digest(spec.model_dump(mode="json")),
            "started_at": time.time(),
        }

    def _metrics(self, root: Path, spec: ExperimentSpec) -> dict[str, float]:
        try:
            raw = strict_json(_read(root, spec.metrics_file, 1024 * 1024))
        except (ValueError, OSError, RecursionError):
            raise ExecutionError("Experiment metrics are missing or invalid JSON") from None
        if not isinstance(raw, dict) or not raw:
            raise ExecutionError("Experiment metrics must be a nonempty JSON object")
        result: dict[str, float] = {}
        for name, value in raw.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ExecutionError("Every experiment metric must be a finite number")
            try:
                number = float(value)
            except OverflowError:
                raise ExecutionError("Every experiment metric must be a finite number") from None
            if not math.isfinite(number):
                raise ExecutionError("Every experiment metric must be a finite number")
            result[name] = number
        return result

    def _result(
        self,
        root: Path,
        spec: ExperimentSpec,
        process: _Process,
        provenance: dict[str, Any],
        *,
        job_id: str | None = None,
    ) -> ExperimentResult:
        status: Any = (
            "timeout" if process.timed_out else "completed" if process.returncode == 0 else "failed"
        )
        metrics: dict[str, float] = {}
        stderr = process.stderr
        if status == "completed" and not provenance.get("command_only", False):
            try:
                metrics = self._metrics(root, spec)
                artifacts = {}
                for path in spec.metadata.get("measurement_artifacts", []):
                    artifacts[path] = file_identity(root, path)
                provenance["measurement_artifacts"] = artifacts
                provenance["research_protocol"] = spec.metadata.get("research_protocol", {})
            except (ExecutionError, OSError) as error:
                status = "failed"
                stderr += "\n" + str(error)
        result = ExperimentResult(
            id=spec.id,
            status=status,
            metrics=metrics,
            stdout=str(redact(process.stdout)),
            stderr=str(redact(stderr)),
            exit_code=process.returncode,
            job_id=job_id,
            duration_seconds=process.duration,
            provenance=provenance,
        )
        if status == "completed" and not provenance.get("command_only", False):
            from .integrity import capture_statistical_analyses

            capture_statistical_analyses(
                result,
                root,
                spec.metadata.get("analysis_artifacts", []),
                spec.metadata.get("analysis_inputs", []),
            )
        return result

    def _prepare_evaluator(
        self, root: Path, spec: ExperimentSpec, provenance: dict[str, Any]
    ) -> tuple[Path | None, list[str]]:
        evaluator: list[str] = spec.metadata.get("evaluator_argv", [])
        if not evaluator and not spec.metadata.get("protected_files"):
            return None, []
        protected: list[str] = spec.metadata["protected_files"]
        snapshot = Path(tempfile.mkdtemp(prefix=_PREFIX + "protected-", dir=root.parent))
        hashes: dict[str, str] = {}
        try:
            for relative in protected:
                copy_file(root, relative, snapshot)
                hashes[relative] = str(file_identity(snapshot, relative)["sha256"])
            location = (
                Path("/autoresearch-protected") if self.config.backend == "docker" else snapshot
            )
            if spec.metadata.get("analysis_artifacts"):
                name = _PREFIX + "analysis-inputs.json"
                _write(
                    snapshot,
                    name,
                    json.dumps(spec.metadata.get("analysis_inputs", [])),
                    internal=True,
                )
                provenance["analysis_inputs_path"] = str(location / name)
                registration = provenance.get("registered_statistical_plan")
                if registration:
                    plan_name = _PREFIX + "statistical-plan.json"
                    _write(snapshot, plan_name, registration["content"], internal=True)
                    provenance["statistical_plan_path"] = str(location / plan_name)
            command = [str(location / arg) if arg in protected else arg for arg in evaluator]
            provenance.update(
                {
                    "evaluator_argv": evaluator,
                    "evaluator_isolated": self.config.backend == "docker",
                    "protected_sha256": hashes,
                }
            )
            return snapshot, command
        except BaseException:
            shutil.rmtree(snapshot)
            raise

    def _write_runner(self, root: Path, spec: ExperimentSpec, evaluator: list[str]) -> None:
        for filename in (_STDOUT, _STDERR):
            with _parent(root, filename, internal=True) as (descriptor, name):
                try:
                    info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise ExecutionError("Runner log path must be a regular file")
                    os.unlink(name, dir_fd=descriptor)
                except FileNotFoundError:
                    pass
        _write(root, _PREFIX + "slurm-runner.py", _SLURM_RUNNER, internal=True)
        _write(
            root,
            _PREFIX + "slurm-config.json",
            json.dumps(
                {
                    "argv": spec.argv,
                    "evaluator_argv": evaluator,
                    "metrics_file": spec.metrics_file,
                    "analysis_artifacts": spec.metadata.get("analysis_artifacts", []),
                    "timeout_seconds": spec.timeout_seconds,
                    "max_log_bytes": self.config.max_log_bytes,
                }
            ),
            internal=True,
        )

    def run(self, spec: ExperimentSpec, *, command_only: bool = False) -> ExperimentResult:
        root = self._validate(spec)
        if self.config.backend == "slurm" and (root / _META).exists():
            try:
                record = strict_json(_read(root, _META, 1024 * 1024, internal=True))
                if record["id"] != spec.id or record["provenance"]["spec_sha256"] != _digest(
                    spec.model_dump(mode="json")
                ):
                    raise ExecutionError("Existing Slurm submission has a different specification")
                if record["provenance"].get("command_only", False) != command_only:
                    raise ExecutionError("Existing Slurm submission has a different execution mode")
                if not record.get("job_id"):
                    raise ExecutionError(
                        "Slurm submission outcome is uncertain; reconcile the saved job name with the scheduler before resubmission"
                    )
                self._job(record["job_id"])
                return ExperimentResult(
                    id=spec.id,
                    status="pending",
                    job_id=record["job_id"],
                    provenance=record["provenance"],
                )
            except (KeyError, TypeError, OSError):
                raise ExecutionError("Existing Slurm checkpoint is invalid") from None
        for edit in spec.files:
            _write(root, edit.path, edit.content)
        # Stale metrics must never be mistaken for a new successful experiment.
        for artifact in [spec.metrics_file, *spec.metadata.get("measurement_artifacts", [])]:
            if artifact in spec.metadata.get("protected_files", []):
                raise ExecutionError("Measurement output cannot replace a protected input")
            with _parent(root, artifact, create=True) as (descriptor, name):
                try:
                    info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise ExecutionError("Measurement target must be a regular file")
                    os.unlink(name, dir_fd=descriptor)
                except FileNotFoundError:
                    pass
        provenance = self._provenance(root, spec)
        provenance["command_only"] = command_only
        snapshot, evaluator = self._prepare_evaluator(root, spec, provenance)
        try:
            if self.config.backend == "slurm":
                return self._submit(root, spec, provenance, evaluator)
            return self._run_sync(root, spec, provenance, snapshot, evaluator)
        finally:
            if snapshot is not None and self.config.backend != "slurm":
                shutil.rmtree(snapshot)

    def _run_sync(
        self,
        root: Path,
        spec: ExperimentSpec,
        provenance: dict[str, Any],
        snapshot: Path | None,
        evaluator: list[str],
    ) -> ExperimentResult:
        env = self._env(spec)
        if provenance.get("analysis_inputs_path"):
            env["AUTORESEARCH_ANALYSIS_INPUTS"] = provenance["analysis_inputs_path"]
        if provenance.get("statistical_plan_path"):
            env["AUTORESEARCH_STATISTICAL_PLAN"] = provenance["statistical_plan_path"]
        container_name: str | None = None
        experiment_argv = spec.argv
        if evaluator:
            self._write_runner(root, spec, evaluator)
            runner_root = Path("/workspace") if self.config.backend == "docker" else root
            experiment_argv = [
                "python3",
                str(runner_root / (_PREFIX + "slurm-runner.py")),
                str(runner_root / (_PREFIX + "slurm-config.json")),
            ]
        if self.config.backend == "local":
            executable = self._tool(experiment_argv[0])
            env["PATH"] = str(Path(executable).parent) + os.pathsep + os.defpath
            argv = [executable, *experiment_argv[1:]]
            provenance["executable"] = str(redact(executable))
            provenance["environment"]["env"] = env
            provenance["environment_sha256"] = _digest(provenance["environment"])
        else:
            container_name = "autoresearch-" + uuid.uuid4().hex
            argv = [
                self._tool("docker"),
                "run",
                "--rm",
                "--name",
                container_name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "256",
                "--cpus",
                str(self.config.cpus),
                "--memory",
                f"{self.config.memory_mb}m",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=128m",  # noqa: S108 - container-private memory filesystem
                "--workdir",
                "/workspace",
                "--mount",
                f"type=bind,source={root},target=/workspace",
            ]
            if self.config.gpus:
                argv += ["--gpus", str(self.config.gpus)]
            if snapshot is not None:
                argv += [
                    "--mount",
                    f"type=bind,source={snapshot},target=/autoresearch-protected,readonly",
                ]
                # Protect the working-tree copies too: tests and generated code
                # must not replace the protocol while the trusted copy survives.
                for relative in spec.metadata.get("protected_files", []):
                    if "," in relative:
                        raise ExecutionError("Protected Docker paths cannot contain commas")
                    argv += [
                        "--mount",
                        f"type=bind,source={snapshot / relative},target=/workspace/{relative},readonly",
                    ]
            for mount in provenance["data_provenance"]["readonly_mounts"]:
                argv += [
                    "--mount",
                    f"type=bind,source={mount['source']},target={mount['target']},readonly",
                ]
            for name, value in env.items():
                if name != "PATH":
                    argv += ["--env", f"{name}={value}"]
            argv += [self.config.docker_image, *experiment_argv]
        # The host Docker client needs its local context (not passed into the
        # workload). HOME contains no credential value; provider keys and proxy
        # variables remain absent. This supports Docker Desktop socket paths.
        host_env = {**env, "HOME": str(Path.home())} if container_name else env
        try:
            process = _run(
                argv,
                cwd=root,
                env=host_env,
                timeout=spec.timeout_seconds,
                limit=self.config.max_log_bytes,
            )
            if container_name:
                image_info = _run(
                    [
                        self._tool("docker"),
                        "image",
                        "inspect",
                        "--format",
                        "{{.Id}}",
                        self.config.docker_image,
                    ],
                    cwd=root,
                    env=host_env,
                    timeout=15,
                    limit=4096,
                )
                if image_info.returncode == 0 and re.fullmatch(
                    r"sha256:[a-f0-9]{64}", image_info.stdout.strip()
                ):
                    provenance["environment"]["resolved_image_id"] = image_info.stdout.strip()
                    provenance["environment_sha256"] = _digest(provenance["environment"])
        except OSError:
            raise ExecutionError("Experiment process could not be started") from None
        finally:
            if container_name:
                _run(
                    [self._tool("docker"), "rm", "--force", container_name],
                    cwd=root,
                    env=host_env,
                    timeout=15,
                    limit=4096,
                )
        if evaluator:
            process.stdout = self._log(root, _STDOUT)
            process.stderr = (self._log(root, _STDERR) + process.stderr)[
                : self.config.max_log_bytes
            ]
            process.timed_out = process.timed_out or process.returncode == 124
        return self._result(root, spec, process, provenance)

    def _submit(
        self, root: Path, spec: ExperimentSpec, provenance: dict[str, Any], evaluator: list[str]
    ) -> ExperimentResult:
        self._write_runner(root, spec, evaluator)
        env = self._env(spec)
        if provenance.get("analysis_inputs_path"):
            env["AUTORESEARCH_ANALYSIS_INPUTS"] = provenance["analysis_inputs_path"]
        if provenance.get("statistical_plan_path"):
            env["AUTORESEARCH_STATISTICAL_PLAN"] = provenance["statistical_plan_path"]
        invocation = [
            "/usr/bin/env",
            "-i",
            *[f"{k}={v}" for k, v in env.items()],
            "python3",
            str(root / (_PREFIX + "slurm-runner.py")),
            str(root / (_PREFIX + "slurm-config.json")),
        ]
        script = "#!/bin/sh\nset -eu\numask 077\nexec " + shlex.join(invocation) + "\n"
        _write(root, _PREFIX + "job.sh", script, internal=True)
        job_name = "autoresearch-" + provenance["spec_sha256"][:20]
        argv = [
            self._tool("sbatch"),
            "--parsable",
            "--export=NONE",
            "--chdir",
            str(root),
            "--job-name",
            job_name,
            "--output",
            str(root / (_PREFIX + "scheduler.out")),
            "--error",
            str(root / (_PREFIX + "scheduler.err")),
            "--time",
            str(max(1, math.ceil(spec.timeout_seconds / 60))),
            "--mem",
            f"{self.config.memory_mb}M",
            "--cpus-per-task",
            str(self.config.cpus),
        ]
        if self.config.gpus:
            argv += ["--gpus", str(self.config.gpus)]
        if self.config.slurm_partition:
            argv += ["--partition", self.config.slurm_partition]
        if self.config.slurm_account:
            argv += ["--account", self.config.slurm_account]
        argv.append(str(root / (_PREFIX + "job.sh")))
        # Write-ahead intent prevents duplicate research jobs after a process
        # crash between submission and recording the scheduler-assigned id.
        _write(
            root,
            _META,
            json.dumps(
                {
                    "id": spec.id,
                    "job_id": None,
                    "job_name": job_name,
                    "provenance": provenance,
                },
                sort_keys=True,
            ),
            internal=True,
        )
        process = _run(argv, cwd=root, env=env, timeout=30, limit=self.config.max_log_bytes)
        if process.returncode or process.timed_out:
            return self._result(root, spec, process, provenance)
        job_id = process.stdout.strip()
        self._job(job_id)
        record = {"id": spec.id, "job_id": job_id, "provenance": provenance}
        _write(root, _META, json.dumps(record, sort_keys=True), internal=True)
        return ExperimentResult(id=spec.id, status="pending", job_id=job_id, provenance=provenance)

    def _job(self, job_id: str) -> tuple[str, list[str]]:
        if not re.fullmatch(r"[0-9]+(?:;[A-Za-z0-9_][A-Za-z0-9_.-]*)?", job_id):
            raise ExecutionError("Invalid Slurm job identifier")
        parts = job_id.split(";", 1)
        return parts[0], ["--clusters", parts[1]] if len(parts) == 2 else []

    def _log(self, root: Path, name: str) -> str:
        try:
            return _read(root, name, self.config.max_log_bytes, internal=True)
        except (ExecutionError, OSError):
            return ""

    def poll(self, spec: ExperimentSpec, job_id: str) -> ExperimentResult:
        if self.config.backend != "slurm":
            raise ExecutionError("Only Slurm execution supports asynchronous polling")
        root = self._validate(spec)
        number, cluster = self._job(job_id)
        try:
            record = strict_json(_read(root, _META, 1024 * 1024, internal=True))
            if record["id"] != spec.id or record["job_id"] != job_id:
                raise ValueError("Wrong job")
            provenance = record["provenance"]
            if provenance["spec_sha256"] != _digest(spec.model_dump(mode="json")):
                raise ValueError("Changed specification")
        except (KeyError, TypeError, ValueError, OSError):
            raise ExecutionError(
                "Slurm checkpoint is missing or does not match this experiment"
            ) from None
        env = self._env(spec)
        queued = _run(
            [self._tool("squeue"), *cluster, "--jobs", number, "--noheader", "--format=%T"],
            cwd=root,
            env=env,
            timeout=30,
            limit=4096,
        )
        stdout = str(redact(self._log(root, _STDOUT)))
        stderr = str(redact(self._log(root, _STDERR)))
        pending = ExperimentResult(
            id=spec.id,
            status="pending",
            job_id=job_id,
            stdout=stdout,
            stderr=stderr,
            provenance=provenance,
        )
        active_states = {
            "PENDING",
            "RUNNING",
            "CONFIGURING",
            "COMPLETING",
            "SUSPENDED",
            "REQUEUED",
            "RESIZING",
        }
        if queued.returncode == 0 and any(
            value.strip() in active_states for value in queued.stdout.splitlines()
        ):
            return pending
        accounting = _run(
            [
                self._tool("sacct"),
                *cluster,
                "--jobs",
                number,
                "--noheader",
                "--parsable2",
                "--format=JobIDRaw,State,ExitCode,ElapsedRaw",
            ],
            cwd=root,
            env=env,
            timeout=30,
            limit=self.config.max_log_bytes,
        )
        if accounting.returncode:
            pending.stderr += "\nSlurm accounting query unavailable; awaiting scheduler recovery."
            return pending
        for line in accounting.stdout.splitlines():
            values = line.strip().split("|")
            if len(values) < 4 or values[0] != number:
                continue
            state = values[1].split()[0].rstrip("+")
            if state in {
                "PENDING",
                "RUNNING",
                "CONFIGURING",
                "COMPLETING",
                "SUSPENDED",
                "REQUEUED",
                "RESIZING",
            }:
                return pending
            try:
                code_text, signal_text = values[2].split(":", 1)
                code, signal_number = int(code_text), int(signal_text)
                code = code if code else 128 + signal_number if signal_number else 0
                duration = max(0, int(values[3]))
            except (ValueError, IndexError):
                return pending
            timed_out = state == "TIMEOUT" or code == 124
            process = _Process(
                stdout, stderr, code if state == "COMPLETED" else code or 1, duration, timed_out
            )
            result = self._result(root, spec, process, provenance, job_id=job_id)
            if state == "CANCELLED":
                result.status = "cancelled"
            result.provenance["slurm_state"] = state
            return result
        # Slurm accounting is eventually consistent; absence is not failure.
        return pending

    def cancel(self, job_id: str) -> None:
        if self.config.backend != "slurm":
            raise ExecutionError("Cancellation by job identifier is available only for Slurm")
        number, cluster = self._job(job_id)
        process = _run(
            [self._tool("scancel"), *cluster, number],
            cwd=Path.cwd(),
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            timeout=30,
            limit=4096,
        )
        if process.returncode or process.timed_out:
            raise ExecutionError("Slurm cancellation failed")
