"""Managed SSH access to a remote controller; research execution remains remote."""

from __future__ import annotations

import atexit
import base64
import glob
import hashlib
import http.client
import importlib.metadata
import json
import os
import re
import select
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .runtime_support.process import ProcessResult
from .source_policy import source_is_excluded
from .ssh_auth import AuthenticationSession

_HOST = re.compile(
    r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?(?:[A-Za-z0-9][A-Za-z0-9_.:-]*|\[[a-fA-F0-9:]+\])\Z"
)
_REQUIREMENTS = ["httpx==0.28.1", "keyring==25.7.0", "pydantic==2.12.5", "textual==8.2.8"]
_SUFFIXES = {".py", ".json", ".md", ".txt", ".html", ".css", ".js", ".toml"}
_READY_TIMEOUT = 5.0
_AUTH_WAIT = 15.0
_MONITOR_INTERVAL = 2.0
_RECONNECT_DELAYS = (0.5, 1.0, 2.0)


class RemoteProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    host: str
    port: int | None = Field(default=None, ge=1, le=65535)
    identity_file: str | None = None
    directory: str = "~/.local/share/autoresearch/remote"
    python: str = "python3"
    state_dir: str | None = None
    db_dir: str | None = None
    config_path: str | None = None

    @field_validator("host")
    @classmethod
    def host_is_destination(cls, value: str) -> str:
        if not _HOST.fullmatch(value):
            raise ValueError("Use an SSH alias or hostname, optionally preceded by user@.")
        return value

    @field_validator("directory", "python", "state_dir", "db_dir", "config_path", "identity_file")
    @classmethod
    def text_is_single_argument(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip()
            or len(value) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("Paths and interpreter names must be nonempty single-line values.")
        return value

    @field_validator("directory")
    @classmethod
    def directory_is_dedicated(cls, value: str) -> str:
        if value.rstrip("/") in {"", "~", "."}:
            raise ValueError(
                "Choose a dedicated installation directory, not the home or root directory."
            )
        return value

    @field_validator("python")
    @classmethod
    def python_is_executable(cls, value: str) -> str:
        if not value.startswith("/") and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value):
            raise ValueError(
                "Python must be an absolute executable path or command name; expand ~ explicitly."
            )
        return value


class RemoteError(RuntimeError):
    """An operational error containing no remote output or authentication material."""


def ssh_hosts(config: Path | None = None) -> list[str]:
    """Discover literal Host choices; OpenSSH itself remains the configuration authority."""
    found: set[str] = set()
    seen: set[Path] = set()
    base = Path.home() / ".ssh"

    def visit(path: Path, depth: int = 0) -> None:
        if depth > 16 or len(seen) >= 128:
            return
        path = path.expanduser().resolve()
        if path in seen:
            return
        seen.add(path)
        try:
            if path.stat().st_size > 1024 * 1024:
                return
            lines = path.read_text().splitlines()
        except (OSError, UnicodeError):
            return
        for line in lines:
            try:
                words = shlex.split(line, comments=True)
            except ValueError:
                continue
            if not words:
                continue
            # OpenSSH permits Keyword=value as well as Keyword value.
            if "=" in words[0]:
                key, value = words[0].split("=", 1)
                words = [key, value, *words[1:]]
            key = words[0].lower()
            if key == "host":
                found.update(alias for alias in words[1:] if _HOST.fullmatch(alias))
            elif key == "include":
                for pattern in words[1:]:
                    expanded = Path(pattern).expanduser()
                    if not expanded.is_absolute():
                        expanded = base / expanded
                    for included in sorted(glob.glob(str(expanded))):
                        visit(Path(included), depth + 1)

    visit(config or base / "config")
    return sorted(found, key=str.casefold)


_LAUNCH = r"""import json, os, shutil, sys
request = json.loads(sys.argv[1])
directory = os.path.expanduser(request['directory'])
python = os.path.join(directory, 'venv', 'bin', 'python')
if not os.path.isfile(python):
    candidates = [shutil.which(p) for p in ('python3.13', 'python3.12', 'python3.11')]
    print(json.dumps({'status':'not_installed', 'message':'Install the remote runtime first. Python 3.11 or newer is required.', 'python_version':sys.version.split()[0], 'python_candidates':[p for p in candidates if p]}))
    sys.exit(0)
args = [python, '-m', 'autoresearch.remote_runtime', request['action'], '--directory', directory]
for key, flag in [('state_dir','--state-dir'), ('db_dir','--db-dir'), ('config_path','--config')]:
    if request.get(key): args += [flag, os.path.expanduser(request[key])]
os.execv(python, args)
"""

# This bootstrap deliberately parses on older Python, to report an actionable version
# error before attempting a venv. Its only source input is the installed package bundle.
_INSTALL = r"""import base64, contextlib, fcntl, json, os, pathlib, shutil, subprocess, sys, tempfile
if sys.version_info < (3, 11):
    candidates = [shutil.which(p) for p in ('python3.13', 'python3.12', 'python3.11')]
    print(json.dumps({'status':'failed', 'message':'Remote Python is too old; select Python 3.11 or newer in the profile.', 'python_candidates':[p for p in candidates if p]}))
    sys.exit(0)
request = json.load(sys.stdin)
root = pathlib.Path(request['directory']).expanduser().absolute()
if root.resolve() in (pathlib.Path('/'), pathlib.Path.home().resolve()): raise RuntimeError('Choose a dedicated installation directory')
if root.is_symlink() or any(p.is_symlink() for p in root.parents): raise RuntimeError('Installation path must not contain a symlink')
root.mkdir(mode=0o700, parents=True, exist_ok=True)
if root.stat().st_uid != os.getuid(): raise RuntimeError('Installation directory must be owned by the current user')
root.chmod(0o700)
fd = os.open(str(root / '.install.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    # Match runtime launch/lifetime locks before touching code or dependencies.
    lock_stack = contextlib.ExitStack()
    for name in ('launch.lock', 'controller.lock'):
        descriptor = os.open(str(root / name), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        guard = lock_stack.enter_context(os.fdopen(descriptor, 'w'))
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status':'failed', 'message':'A controller is active or starting; installation was not changed.'}))
            sys.exit(0)
    marker = root / 'installed.json'
    venv = root / 'venv'
    if marker.is_symlink() or venv.is_symlink(): raise RuntimeError('Unsafe installation path')
    if marker.exists() and json.loads(marker.read_text()).get('sha256') == request['sha256'] and (venv / 'bin/python').is_file():
        print(json.dumps({'status':'installed', 'message':'The requested package is already installed.'}))
        sys.exit(0)
    package = root / ('package-' + request['sha256'])
    package.mkdir(mode=0o700, exist_ok=True)
    if package.is_symlink(): raise RuntimeError('Unsafe package path')
    for name, content in request['files'].items():
        relative = pathlib.PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts: raise RuntimeError('Unsafe package entry')
        target = package.joinpath(*relative.parts)
        cursor = package
        for component in relative.parts[:-1]:
            cursor = cursor / component
            if cursor.is_symlink(): raise RuntimeError('Unsafe package directory')
            cursor.mkdir(mode=0o700, exist_ok=True)
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root.parent): raise RuntimeError('Unsafe package entry')
        descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as output: output.write(base64.b64decode(content, validate=True))
    pyproject = '[build-system]\nrequires = ["hatchling==1.27.0"]\nbuild-backend = "hatchling.build"\n[project]\nname = "metis-research"\nversion = "0.1.0"\nrequires-python = ">=3.11"\ndependencies = ' + json.dumps(request['requirements']) + '\n[project.scripts]\nmetis = "autoresearch.cli:main"\nautoresearch = "autoresearch.cli:main"\n[tool.hatch.build.targets.wheel]\npackages = ["src/autoresearch"]\n'
    if (package / 'pyproject.toml').is_symlink(): raise RuntimeError('Unsafe build configuration')
    (package / 'pyproject.toml').write_text(pyproject)
    subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True, stdout=sys.stderr, stderr=sys.stderr)
    subprocess.run([str(venv / 'bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', str(package)], check=True, stdout=sys.stderr, stderr=sys.stderr)
    descriptor, temporary = tempfile.mkstemp(prefix='.installed-', dir=str(root))
    with os.fdopen(descriptor, 'w') as output:
        json.dump({'sha256': request['sha256']}, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, str(marker))
    print(json.dumps({'status':'installed', 'message':'Remote runtime installed.', 'sha256':request['sha256']}))
"""


@dataclass
class _Tunnel:
    profile: RemoteProfile
    local_port: int
    remote_port: int = 0
    token: str = ""
    status: str = "disconnected"
    message: str = "Disconnected."
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class RemoteManager:
    def __init__(self, root: Path) -> None:
        self.root = root / "remote"
        if self.root.is_symlink():
            raise ValueError("Remote profile directory must not be a symlink.")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self._profile_path = self.root / "profiles.json"
        self._socket_root = Path(tempfile.mkdtemp(prefix="arssh-", dir="/tmp"))  # noqa: S108 - private mkdtemp
        self._lock = threading.RLock()
        self._operations: dict[str, threading.RLock] = {}
        self._sessions: dict[str, AuthenticationSession] = {}
        self._auth_names: dict[str, str] = {}
        self._sockets: dict[str, str] = {}
        self._tunnels: dict[str, _Tunnel] = {}
        self._children: set[subprocess.Popen[bytes]] = set()
        self._termination_lock = threading.Lock()
        self._terminated_children: weakref.WeakSet[subprocess.Popen[bytes]] = weakref.WeakSet()
        self._closing = False
        self._closed = False
        atexit.register(self.close)

    def hosts(self) -> list[str]:
        return ssh_hosts()

    def profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._profile_path.exists():
                return []
            if self._profile_path.is_symlink() or self._profile_path.stat().st_size > 1024 * 1024:
                raise ValueError("Unsafe remote profile file.")
            values = json.loads(self._profile_path.read_text())
            if not isinstance(values, list):
                raise ValueError("Invalid remote profile file.")
            return [RemoteProfile.model_validate(value).model_dump() for value in values]

    def save_profile(self, profile: RemoteProfile) -> dict[str, Any]:
        profile = RemoteProfile.model_validate(profile.model_dump())
        with self._lock:
            profiles = {row["name"]: row for row in self.profiles()}
            old = profiles.get(profile.name)
            if old is not None and old != profile.model_dump():
                self.disconnect(profile.name)
                session = self._session_for(profile.name)
                if session is not None:
                    session.close()
                self._sockets.pop(profile.name, None)
                self._auth_names.pop(profile.name, None)
            profiles[profile.name] = profile.model_dump()
            descriptor, temporary = tempfile.mkstemp(prefix="profiles-", dir=self.root)
            try:
                with os.fdopen(descriptor, "w") as output:
                    json.dump(list(profiles.values()), output, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self._profile_path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return profile.model_dump()

    def _profile(self, name: str) -> RemoteProfile:
        for row in self.profiles():
            if row["name"] == name:
                return RemoteProfile.model_validate(row)
        raise ValueError("Unknown remote profile.")

    def _base(
        self, profile: RemoteProfile, *, batch: bool = True, managed: bool = True
    ) -> list[str]:
        argv = [
            "ssh",
            "-o",
            "ForwardAgent=no",
            "-o",
            "ForwardX11=no",
            "-o",
            "BatchMode=" + ("yes" if batch else "no"),
            "-o",
            "StrictHostKeyChecking=" + ("yes" if batch else "ask"),
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=2",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ControlMaster=no",
        ]
        if profile.port is not None:
            argv += ["-p", str(profile.port)]
        if profile.identity_file:
            argv += ["-i", str(Path(profile.identity_file).expanduser())]
        if managed and profile.name in self._sockets:
            argv += ["-S", self._sockets[profile.name]]
        return argv

    def _run(
        self,
        argv: list[str],
        *,
        data: bytes | None = None,
        timeout: float = 30,
        cleanup: bool = False,
    ) -> ProcessResult:
        started = time.monotonic()
        output = bytearray()
        timed_out = False
        with tempfile.TemporaryFile() as source:
            if data is not None:
                source.write(data)
                source.seek(0)
            with self._lock:
                if self._closed or (self._closing and not cleanup):
                    raise RemoteError("Remote manager is closed.")
                # Child admission and shutdown share the same lock. A process
                # cannot appear after close has taken its cleanup snapshot.
                process = subprocess.Popen(
                    argv,
                    cwd=self.root,
                    stdin=source,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self._children.add(process)
            try:
                assert process.stdout is not None
                while True:
                    if time.monotonic() - started >= timeout:
                        timed_out = True
                        break
                    readable, _, _ = select.select([process.stdout], [], [], 0.1)
                    if readable:
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            break
                        output.extend(chunk[: max(0, 65537 - len(output))])
                        if len(output) > 65536:
                            break
                try:
                    process.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
                except subprocess.TimeoutExpired:
                    timed_out = True
            finally:
                try:
                    self._terminate(process)
                finally:
                    if process.stdout is not None:
                        process.stdout.close()
                    with self._lock:
                        self._children.discard(process)
        if len(output) > 65536:
            return ProcessResult("", "", 1, time.monotonic() - started)
        return ProcessResult(
            output.decode(errors="replace"),
            "",
            process.returncode,
            time.monotonic() - started,
            timed_out,
        )

    def _terminate(self, process: subprocess.Popen[bytes]) -> None:
        with self._termination_lock:
            if process in self._terminated_children:
                return
            self._terminated_children.add(process)
            self._terminate_once(process)

    @staticmethod
    def _terminate_once(process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)

    def _check_master(self, profile: RemoteProfile, *, managed: bool = True) -> bool:
        try:
            result = self._run(
                [*self._base(profile, managed=managed), "-O", "check", profile.host], timeout=5
            )
            return result.returncode == 0 and not result.timed_out
        except (OSError, RemoteError):
            return False

    def _session_for(self, name: str) -> AuthenticationSession | None:
        return self._sessions.get(self._auth_names.get(name, ""))

    def _authenticate(self, profile: RemoteProfile, *, interactive: bool) -> AuthenticationSession:
        with self._lock:
            if self._closed or self._closing:
                raise RemoteError("Remote manager is closing.")
            existing = self._session_for(profile.name)
            if existing is not None and existing.result()["status"] == "authenticating":
                return existing
            if existing is not None and self._check_master(profile):
                return existing
            if existing is not None:
                existing.close()
            # Borrow a configured user-owned master when available, never stop it.
            self._sockets.pop(profile.name, None)
            if self._check_master(profile, managed=False):
                session = AuthenticationSession([], lambda: True, borrowed=True)
            else:
                path = str(
                    self._socket_root / hashlib.sha256(profile.name.encode()).hexdigest()[:16]
                )
                Path(path).unlink(missing_ok=True)
                self._sockets[profile.name] = path
                argv = self._base(profile, batch=not interactive)
                # First command-line setting wins; replace ControlMaster=no explicitly.
                argv[argv.index("ControlMaster=no")] = "ControlMaster=yes"
                argv += [
                    "-o",
                    "ControlPersist=no",
                    "-o",
                    "ClearAllForwardings=yes",
                    "-N",
                    "-T",
                    profile.host,
                ]
                session = AuthenticationSession(argv, lambda: self._check_master(profile))
            self._sessions[session.id] = session
            self._auth_names[profile.name] = session.id
            return session

    def authenticate(self, name: str) -> dict[str, Any]:
        return self._authenticate(self._profile(name), interactive=True).result()

    def authentication(self, session_id: str) -> dict[str, Any]:
        try:
            return self._sessions[session_id].result()
        except KeyError:
            raise ValueError("Unknown authentication session.") from None

    def answer_authentication(self, session_id: str, answer: str) -> dict[str, Any]:
        try:
            return self._sessions[session_id].answer(answer)
        except KeyError:
            raise ValueError("Unknown authentication session.") from None

    def cancel_authentication(self, session_id: str) -> dict[str, Any]:
        try:
            return self._sessions[session_id].close()
        except KeyError:
            raise ValueError("Unknown authentication session.") from None

    def _ensure_master(self, profile: RemoteProfile) -> None:
        session = self._authenticate(profile, interactive=False)
        deadline = time.monotonic() + _AUTH_WAIT
        while session.result()["status"] == "authenticating" and time.monotonic() < deadline:
            time.sleep(0.05)
        if session.result()["status"] != "authenticated":
            raise RemoteError("SSH is not authenticated. Use Sign in to answer SSH or MFA prompts.")

    def _json_command(
        self,
        profile: RemoteProfile,
        command: list[str],
        *,
        data: bytes | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        try:
            result = self._run(
                [*self._base(profile), "-T", profile.host, shlex.join(command)],
                data=data,
                timeout=timeout,
            )
        except OSError:
            raise RemoteError(
                "OpenSSH could not be started. Install the system SSH client."
            ) from None
        if result.timed_out:
            raise RemoteError(
                "Remote command failed or timed out. Check SSH access and the configured Python interpreter."
            )
        try:
            value = json.loads(result.stdout)
            if not isinstance(value, dict) or not isinstance(value.get("status"), str):
                raise ValueError("Invalid response")
            if result.returncode and value["status"] not in {"error", "failed"}:
                raise ValueError("Unexpected command exit")
            return value
        except (ValueError, TypeError):
            raise RemoteError(
                "Remote helper returned an invalid response; check the installed runtime."
            ) from None

    def _helper(self, profile: RemoteProfile, action: str) -> dict[str, Any]:
        request = {**profile.model_dump(), "action": action}
        return self._json_command(profile, [profile.python, "-c", _LAUNCH, json.dumps(request)])

    def _safe_result(self, result: dict[str, Any]) -> dict[str, Any]:
        # Whitelist public readiness fields. Helper descriptors can contain bearer tokens.
        safe = {
            key: result[key]
            for key in (
                "status",
                "host",
                "pid",
                "port",
                "python_version",
                "python_candidates",
                "python",
                "sha256",
                "ready",
                "problems",
                "database_filesystem",
                "slurm",
                "error",
            )
            if key in result
        }
        messages = {
            "running": "Remote controller is running.",
            "stopped": "Remote controller is stopped.",
            "ready": "Remote controller prerequisites are ready.",
            "needs_configuration": "Remote settings need attention; inspect the readiness problems.",
            "not_installed": "Remote runtime is not installed; use Install runtime. Python 3.11 or newer is required.",
            "installed": "Remote runtime installed.",
            "failed": "Remote runtime is not ready. Check Python 3.11+, runtime configuration and durable database storage.",
            "error": "Remote runtime failed. Check its configuration and durable database storage.",
        }
        safe["message"] = messages.get(
            str(result.get("status")), "Remote readiness check completed."
        )
        secrets: list[str] = []

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if re.search(r"token|password|secret|authorization", key, re.I) and isinstance(
                        item, str
                    ):
                        secrets.append(item)
                    else:
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(result)

        def clean(value: Any, depth: int = 0) -> Any:
            if depth > 5:
                return "[truncated]"
            if isinstance(value, dict):
                return {
                    key: clean(item, depth + 1)
                    for key, item in list(value.items())[:50]
                    if not re.search(r"token|password|secret|authorization|url", key, re.I)
                }
            if isinstance(value, list):
                return [clean(item, depth + 1) for item in value[:100]]
            if isinstance(value, str):
                for secret in secrets:
                    if secret:
                        value = value.replace(secret, "[redacted]")
                return value[:4096]
            return value

        cleaned: dict[str, Any] = clean(safe)
        return cleaned

    def probe(self, name: str) -> dict[str, Any]:
        profile = self._profile(name)
        try:
            self._ensure_master(profile)
            return self._safe_result(self._helper(profile, "probe"))
        except (RemoteError, OSError) as error:
            return {
                "status": "failed",
                "host": profile.host,
                "message": str(error)
                if isinstance(error, RemoteError)
                else "SSH connection could not be opened.",
            }

    def _bundle(self, profile: RemoteProfile) -> bytes:
        package = Path(__file__).resolve().parent
        manifest: set[Path] | None = None
        try:
            distribution = importlib.metadata.distribution("metis-research")
            recorded = {
                Path(str(distribution.locate_file(path))).resolve()
                for path in distribution.files or []
                if "autoresearch" in path.parts
            }
            if package / "remote.py" in recorded:
                manifest = recorded
        except importlib.metadata.PackageNotFoundError:
            pass
        if manifest is None:
            # Editable checkouts contain development files that are not the application.
            try:
                tracked = subprocess.run(
                    ["git", "-C", str(package), "ls-files", "-z", "--", "."],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
                if tracked.returncode == 0:
                    manifest = {
                        package / name.decode() for name in tracked.stdout.split(b"\0") if name
                    }
            except (OSError, UnicodeError, subprocess.TimeoutExpired):
                pass
        files: dict[str, str] = {}
        digest = hashlib.sha256(json.dumps(_REQUIREMENTS).encode())
        total = 0
        for path in sorted(package.rglob("*")):
            relative = path.relative_to(package)
            if source_is_excluded(relative) or any(part.startswith(".") for part in relative.parts):
                continue
            if manifest is not None and path not in manifest:
                continue
            if path.is_symlink():
                raise RemoteError(
                    "Installed package contains a symlink; install a clean package first."
                )
            if not path.is_file() or path.suffix not in _SUFFIXES or "__pycache__" in path.parts:
                continue
            # A source-only installation without RECORD/Git still includes only code
            # and the three packaged resource trees, never arbitrary adjacent JSON.
            if (
                manifest is None
                and path.suffix != ".py"
                and relative.parts[0] not in {"assets", "specs", "static"}
            ):
                continue
            content = path.read_bytes()
            total += len(content)
            if total > 32 * 1024 * 1024:
                raise RemoteError("Installed package exceeds the remote bundle size limit.")
            name = "src/autoresearch/" + path.relative_to(package).as_posix()
            digest.update(name.encode() + b"\0" + content)
            files[name] = base64.b64encode(content).decode()
        return json.dumps(
            {
                "directory": profile.directory,
                "files": files,
                "requirements": _REQUIREMENTS,
                "sha256": digest.hexdigest(),
            }
        ).encode()

    def install(self, name: str) -> dict[str, Any]:
        profile = self._profile(name)
        try:
            self._ensure_master(profile)
            state = self._helper(profile, "status")
            if state["status"] not in {"stopped", "not_installed"}:
                raise RemoteError(
                    "The remote controller is active or its state is uncertain. Check its host and stop it before installation, or use a separate directory."
                )
            result = self._json_command(
                profile, [profile.python, "-c", _INSTALL], data=self._bundle(profile), timeout=600
            )
            return self._safe_result(result)
        except (RemoteError, OSError) as error:
            return {
                "status": "failed",
                "host": profile.host,
                "message": str(error)
                if isinstance(error, RemoteError)
                else "Remote installation could not be started.",
            }

    @staticmethod
    def _port() -> int:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    def _forward(self, tunnel: _Tunnel, operation: str) -> bool:
        target = f"127.0.0.1:{tunnel.local_port}:127.0.0.1:{tunnel.remote_port}"
        result = self._run(
            [*self._base(tunnel.profile), "-O", operation, "-L", target, tunnel.profile.host],
            timeout=10,
            cleanup=operation == "cancel",
        )
        return result.returncode == 0 and not result.timed_out

    @staticmethod
    def _healthy(tunnel: _Tunnel) -> bool:
        connection = http.client.HTTPConnection("127.0.0.1", tunnel.local_port, timeout=1)
        try:
            connection.request(
                "GET", "/api/remote-health", headers={"Authorization": "Bearer " + tunnel.token}
            )
            response = connection.getresponse()
            data = response.read(8193)
            payload = json.loads(data)
            return (
                response.status == 200
                and len(data) <= 8192
                and isinstance(payload, dict)
                and payload.get("status") == "running"
            )
        except (OSError, ValueError, http.client.HTTPException):
            return False
        finally:
            connection.close()

    def _establish(self, tunnel: _Tunnel) -> None:
        if tunnel.stop.is_set():
            raise RemoteError("Tunnel disconnected.")
        self._ensure_master(tunnel.profile)
        descriptor = self._helper(tunnel.profile, "start")
        if tunnel.stop.is_set():
            raise RemoteError("Tunnel disconnected.")
        if descriptor.get("status") != "running":
            safe = self._safe_result(descriptor)
            raise RemoteError(str(safe.get("error") or safe["message"]))
        port, token = descriptor.get("port"), descriptor.get("token")
        if (
            descriptor.get("status") != "running"
            or isinstance(port, bool)
            or not isinstance(port, int)
            or not 0 < port < 65536
            or not isinstance(token, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token)
        ):
            raise RemoteError(
                "Remote controller did not become ready. Probe the profile and check its runtime configuration."
            )
        tunnel.remote_port, tunnel.token = port, token
        if not self._forward(tunnel, "forward"):
            raise RemoteError("SSH could not create the local forwarding port.")
        if tunnel.stop.is_set():
            self._forward(tunnel, "cancel")
            raise RemoteError("Tunnel disconnected.")
        deadline = time.monotonic() + _READY_TIMEOUT
        while time.monotonic() < deadline and not tunnel.stop.is_set():
            if self._healthy(tunnel):
                tunnel.status, tunnel.message = "connected", "Remote console is connected."
                return
            tunnel.stop.wait(0.1)
        self._forward(tunnel, "cancel")
        raise RemoteError("SSH forwarding opened but the remote console did not authenticate.")

    def connect(self, name: str) -> dict[str, Any]:
        profile = self._profile(name)
        with self._lock:
            operation = self._operations.setdefault(name, threading.RLock())
        with operation:
            existing = self._tunnels.get(name)
            if existing is not None and existing.status == "connected" and self._healthy(existing):
                return self.status(name)
            if existing is not None:
                self.disconnect(name)
            tunnel = _Tunnel(profile, self._port())
            self._tunnels[name] = tunnel
            try:
                self._establish(tunnel)
                tunnel.thread = threading.Thread(
                    target=self._monitor, args=(tunnel,), name="ssh-tunnel", daemon=True
                )
                tunnel.thread.start()
            except (RemoteError, OSError) as error:
                tunnel.status = "failed"
                tunnel.message = (
                    str(error)
                    if isinstance(error, RemoteError)
                    else "Connection failed. Check SSH access and the remote runtime."
                )
                tunnel.token = ""
            return self.status(name)

    def _monitor(self, tunnel: _Tunnel) -> None:
        while not tunnel.stop.wait(_MONITOR_INTERVAL):
            if self._healthy(tunnel):
                continue
            tunnel.status, tunnel.message = (
                "reconnecting",
                "SSH connection interrupted; reconnecting.",
            )
            restored = False
            for delay in _RECONNECT_DELAYS:
                if tunnel.stop.wait(delay):
                    return
                try:
                    self._forward(tunnel, "cancel")
                    self._establish(tunnel)
                    restored = True
                    break
                except (RemoteError, OSError):
                    continue
            if not restored:
                tunnel.status, tunnel.message = (
                    "failed",
                    "Automatic reconnect stopped. Sign in again if needed, then reconnect.",
                )
                tunnel.token = ""
                return

    def status(self, name: str) -> dict[str, Any]:
        profile = self._profile(name)
        tunnel = self._tunnels.get(name)
        result: dict[str, Any] = {
            "status": tunnel.status if tunnel else "disconnected",
            "host": profile.host,
            "message": tunnel.message if tunnel else "Not connected.",
        }
        if tunnel is not None:
            result["local_port"] = tunnel.local_port
            if tunnel.status == "connected":
                result["url"] = (
                    f"http://127.0.0.1:{tunnel.local_port}/#remote-token={quote(tunnel.token, safe='')}"
                )
        return result

    def disconnect(self, name: str) -> dict[str, Any]:
        tunnel = self._tunnels.pop(name, None)
        profile = tunnel.profile if tunnel is not None else self._profile(name)
        if tunnel is not None:
            tunnel.stop.set()
            if tunnel.thread is not None and tunnel.thread is not threading.current_thread():
                tunnel.thread.join(timeout=6)
            if tunnel.remote_port:
                try:
                    self._forward(tunnel, "cancel")
                except (RemoteError, OSError):
                    pass
            tunnel.token = ""
        return {
            "status": "disconnected",
            "host": profile.host,
            "message": "Tunnel closed. Remote research continues.",
        }

    def close(self) -> None:
        with self._lock:
            if self._closed or self._closing:
                return
            self._closing = True
            for tunnel in list(self._tunnels.values()):
                tunnel.stop.set()
            children = list(self._children)
        cleanup_failed = False
        for process in children:
            try:
                self._terminate(process)
            except (OSError, subprocess.SubprocessError):
                cleanup_failed = True
        for name in list(self._tunnels):
            try:
                self.disconnect(name)
            except (OSError, RemoteError, subprocess.SubprocessError):
                cleanup_failed = True
        for session in self._sessions.values():
            try:
                session.close()
            except (OSError, subprocess.SubprocessError):
                cleanup_failed = True
        self._closed = True
        if not cleanup_failed:
            shutil.rmtree(self._socket_root, ignore_errors=True)
        atexit.unregister(self.close)
        if cleanup_failed:
            raise RemoteError(
                "SSH cleanup failed; some local process termination could not be confirmed."
            )
