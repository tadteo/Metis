"""Private, detached controller lifecycle on a user-owned SSH host.

Called by the managed SSH transport. Only application code is installed remotely;
research configuration and provider credentials remain on that host.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hmac
import http.client
import json
import os
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

NETWORK_FILESYSTEMS = {"nfs", "nfs4", "cifs", "smbfs", "lustre", "gpfs", "ceph", "fuse.sshfs"}


def filesystem_type(path: Path) -> str | None:
    """Identify known unsafe WAL storage on Linux without invoking a shell."""
    mounts = Path("/proc/mounts")
    if not mounts.exists():
        return None
    resolved = path.expanduser().resolve()
    matches: list[tuple[int, str]] = []
    for line in mounts.read_text().splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        mount = Path(fields[1].replace("\\040", " ").replace("\\134", "\\"))
        if resolved == mount or mount in resolved.parents:
            matches.append((len(str(mount)), fields[2]))
    return max(matches)[1] if matches else None


def _private_directory(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.resolve() in {Path("/"), Path.home().resolve()}:
        raise ValueError(
            "Choose a dedicated remote runtime directory, not the filesystem root or home"
        )
    # A user-selected shared parent is fine; a redirected private runtime is not.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("Remote runtime paths must not contain symbolic links")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.stat()
    if info.st_uid != os.getuid():
        raise ValueError("Remote runtime directory must be owned by the current user")
    path.chmod(0o700)
    return path.resolve()


def _open_private(path: Path, flags: int) -> int:
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ValueError("Remote controller files must be regular files owned by this user")
    os.fchmod(fd, 0o600)
    return fd


@contextlib.contextmanager
def _lock(path: Path, *, blocking: bool = True) -> Iterator[None]:
    fd = _open_private(path, os.O_CREAT | os.O_RDWR)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(fd, flags)
        yield
    finally:
        os.close(fd)


def _read_descriptor(directory: Path) -> dict[str, Any] | None:
    try:
        fd = _open_private(directory / "controller.json", os.O_RDONLY)
    except FileNotFoundError:
        return None
    with os.fdopen(fd) as stream:
        value = json.load(stream)
    if (
        not isinstance(value, dict)
        or type(value.get("port")) is not int
        or not 1 <= value["port"] <= 65535
        or type(value.get("pid")) is not int
        or value["pid"] < 1
        or not isinstance(value.get("token"), str)
        or len(value["token"]) < 32
        or not isinstance(value.get("host"), str)
    ):
        raise ValueError("Invalid private controller descriptor; inspect the runtime directory")
    return value


def _write_descriptor(directory: Path, value: dict[str, Any]) -> None:
    temporary = directory / f".controller-{secrets.token_hex(8)}.json"
    fd = _open_private(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / "controller.json")
    finally:
        temporary.unlink(missing_ok=True)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def controller_status(directory: Path) -> dict[str, Any]:
    descriptor = _read_descriptor(directory)
    if descriptor is None:
        return {"status": "stopped", "host": socket.gethostname()}
    if descriptor["host"] != socket.gethostname():
        return {
            "status": "other_host",
            "host": descriptor["host"],
            "message": "A controller belongs to another host. Connect to that exact host to reconnect.",
        }
    if not _alive(descriptor["pid"]):
        return {"status": "stopped", "host": descriptor["host"]}
    connection = http.client.HTTPConnection("127.0.0.1", descriptor["port"], timeout=2)
    try:
        connection.request(
            "GET", "/api/bootstrap", headers={"Authorization": f"Bearer {descriptor['token']}"}
        )
        response = connection.getresponse()
        data = json.loads(response.read(1024 * 1024))
        if response.status == 200 and hmac.compare_digest(
            str(data.get("token", "")), descriptor["token"]
        ):
            return {**descriptor, "status": "running"}
    except (OSError, ValueError, http.client.HTTPException):
        pass
    finally:
        connection.close()
    return {
        "status": "unresponsive",
        "host": descriptor["host"],
        "pid": descriptor["pid"],
        "message": "The recorded controller process exists but is not ready; refusing a duplicate.",
    }


def _settings(
    directory: Path,
    state_dir: Path | None,
    db_dir: Path | None,
    config: Path | None,
) -> dict[str, str | None]:
    state_root = (state_dir or directory / "state").expanduser().resolve()
    database_root = (db_dir or state_root).expanduser().resolve()
    return {
        "state_dir": str(state_root),
        "db_dir": str(database_root),
        "config": str(config.expanduser().resolve()) if config else None,
    }


def probe(
    directory: Path,
    *,
    state_dir: Path | None = None,
    db_dir: Path | None = None,
    config: Path | None = None,
) -> dict[str, Any]:
    settings = _settings(directory, state_dir, db_dir, config)
    filesystem = filesystem_type(Path(str(settings["db_dir"])))
    problems = []
    if filesystem in NETWORK_FILESYSTEMS:
        problems.append(
            f"Database directory uses {filesystem}. Choose persistent host-local storage for the "
            "database directory; keep experiment workspaces on shared storage. Temporary scratch "
            "does not provide durable research history."
        )
    if config and not config.expanduser().is_file():
        problems.append("The selected remote research configuration file does not exist.")
    status = controller_status(directory) if directory.exists() else {"status": "stopped"}
    # Probe output is diagnostic: never include the private browser capability.
    status = {key: value for key, value in status.items() if key != "token"}
    return {
        "status": "ready" if not problems else "needs_configuration",
        "ready": not problems,
        "host": socket.gethostname(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "settings": settings,
        "database_filesystem": filesystem,
        "slurm": {
            name: shutil.which(name) is not None
            for name in ("sbatch", "squeue", "sacct", "scancel")
        },
        "controller": status,
        "problems": problems,
    }


def start_controller(
    directory: Path,
    *,
    state_dir: Path | None = None,
    db_dir: Path | None = None,
    config: Path | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    directory = _private_directory(directory)
    settings = _settings(directory, state_dir, db_dir, config)
    with _lock(directory / "launch.lock"):
        existing = controller_status(directory)
        if existing["status"] == "running":
            if existing.get("settings") != settings:
                raise ValueError(
                    "A controller is already running with different paths/configuration"
                )
            return existing
        if existing["status"] != "stopped":
            raise RuntimeError(str(existing.get("message", "Controller unavailable")))
        report = probe(directory, state_dir=state_dir, db_dir=db_dir, config=config)
        if not report["ready"]:
            raise ValueError(" ".join(report["problems"]))
        command = [
            sys.executable,
            "-m",
            "autoresearch.remote_runtime",
            "_serve",
            "--directory",
            str(directory),
            "--state-dir",
            str(settings["state_dir"]),
            "--db-dir",
            str(settings["db_dir"]),
        ]
        if settings["config"]:
            command.extend(["--config", str(settings["config"])])
        log_fd = _open_private(directory / "controller.log", os.O_CREAT | os.O_WRONLY | os.O_APPEND)
        try:
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,
                close_fds=True,
                cwd=directory,
            )
        finally:
            os.close(log_fd)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(
                    "Remote controller exited during startup. Inspect its private controller.log."
                )
            status = controller_status(directory)
            if status["status"] == "running" and status.get("pid") == child.pid:
                return status
            time.sleep(0.1)
        # Do not start another controller when startup acknowledgement was lost.
        raise RuntimeError(
            "Controller startup is still unresolved. Check status and the private controller.log before retrying."
        )


def _serve(
    directory: Path, state_dir: Path | None, db_dir: Path | None, config: Path | None
) -> None:
    from .config import load_config
    from .store import Store
    from .web import ResearchServer

    directory = _private_directory(directory)
    settings = _settings(directory, state_dir, db_dir, config)
    with _lock(directory / "controller.lock", blocking=False):
        # Recheck in the child: a managed controller must never silently use NFS WAL.
        report = probe(directory, state_dir=state_dir, db_dir=db_dir, config=config)
        if not report["ready"]:
            raise ValueError(" ".join(report["problems"]))
        token = secrets.token_urlsafe(32)
        store = Store(Path(str(settings["state_dir"])), db_dir=Path(str(settings["db_dir"])))
        server = ResearchServer(
            store,
            config=load_config(config) if config else None,
            port=0,
            token=token,
            managed_remote=True,
            remote_label=socket.gethostname(),
        )
        descriptor = {
            "status": "running",
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "port": server.server_address[1],
            "token": token,
            "settings": settings,
        }
        _write_descriptor(directory, descriptor)
        stopping = threading.Event()

        def shutdown(signum: int, frame: Any) -> None:
            del signum, frame
            if not stopping.is_set():
                stopping.set()
                threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            server.server_close()
            current = _read_descriptor(directory)
            if current and current["token"] == token:
                (directory / "controller.json").unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Managed SSH controller helper")
    parser.add_argument("action", choices=["probe", "start", "status", "_serve"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--db-dir", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(argv)
    directory = args.directory.expanduser().absolute()
    try:
        if args.action == "_serve":
            _serve(directory, args.state_dir, args.db_dir, args.config)
            return 0
        if args.action == "status":
            result = controller_status(directory)
        else:
            operation = probe if args.action == "probe" else start_controller
            result = operation(
                directory, state_dir=args.state_dir, db_dir=args.db_dir, config=args.config
            )
        print(json.dumps(result), flush=True)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
