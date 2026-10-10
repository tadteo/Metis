"""Trusted standalone experiment runner with bounded logs and argv-only execution.

Runs the workload and then, when configured, the protected evaluator. Before the
evaluator starts, protected inputs are restored from the trusted snapshot. When the
runtime gives this runner its own PID namespace (containers, bubblewrap) and asks for
evaluator isolation, every remaining workload process is killed first and the evaluator
gets a fresh HOME and TMPDIR without a Python user site, so background workload processes
and planted start-up files cannot alter its measurement. Compatible with Python 3.6+
because cluster nodes often provide only their system interpreter.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import FrameType
from typing import BinaryIO, NoReturn


def _fail(message: str) -> NoReturn:
    sys.stderr.write("Metis runner: " + message + "\n")
    raise SystemExit(125)


def _inside_workspace(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        _fail("Evaluation path escaped the workspace: " + relative)
    current = Path(".")
    for part in path.parts[:-1]:
        current = current / part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            _fail("Evaluation path parent became a symlink or file: " + relative)
    return path


def _restore(relative: str, source: str) -> None:
    """Replace a protected workspace input with the trusted snapshot copy."""
    target = _inside_workspace(relative)
    parent = Path(".")
    for part in target.parts[:-1]:
        parent = parent / part
        if not parent.exists():
            parent.mkdir(mode=0o700)
    if target.is_symlink():
        target.unlink()
    elif target.exists() and not target.is_file():
        _fail("Protected input was replaced by a directory or special file: " + relative)
    elif target.is_file():
        with open(source, "rb") as trusted, open(str(target), "rb") as current:
            while True:
                expected, actual = trusted.read(1 << 20), current.read(1 << 20)
                if expected != actual:
                    break
                if not expected:
                    return
        try:
            target.unlink()
        except OSError:
            _fail("Protected input could not be restored: " + relative)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with open(source, "rb") as trusted, os.fdopen(fd, "wb") as restored:
        while True:
            chunk = trusted.read(1 << 20)
            if not chunk:
                break
            restored.write(chunk)


def _end_workload_processes() -> None:
    """Kill every other process in this runner's own PID namespace.

    kill(-1) reaches only processes in the caller's namespace and never its init or
    the caller. Outside a fresh namespace it would reach all of the user's processes,
    so refuse unless this runner is the namespace's first or second process.
    """
    if os.getpid() > 2:
        _fail("Evaluator isolation requires a private PID namespace; refusing to evaluate")
    try:
        os.kill(-1, signal.SIGKILL)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            time.sleep(0.05)


def main() -> None:
    config = json.loads(Path(sys.argv[1]).read_text())
    limit = config["max_log_bytes"]
    # Local annotations are not evaluated at run time, so they are safe on Python 3.6.
    logs: list[BinaryIO] = []
    for name in (".autoresearch-stdout.log", ".autoresearch-stderr.log"):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        logs.append(os.fdopen(fd, "wb"))
    remaining = [limit, limit]

    def drain(stream: BinaryIO, index: int) -> None:
        while True:
            data = stream.read(65536)
            if not data:
                break
            logs[index].write(data[: remaining[index]])
            logs[index].flush()
            remaining[index] = max(0, remaining[index] - len(data))

    process: subprocess.Popen[bytes] | None = None

    # Signature annotations are evaluated: keep this one quoted for Python < 3.10.
    def kill(signum: int, frame: "FrameType | None") -> NoReturn:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, kill)
    started = time.monotonic()
    commands = [config["argv"]]
    if config.get("evaluator_argv"):
        commands.append(config["evaluator_argv"])
    code = 1
    environment: dict[str, str] | None = None
    for phase, argv in enumerate(commands):
        if phase:
            if config.get("isolate_evaluator"):
                _end_workload_processes()
                private = tempfile.mkdtemp(prefix="metis-evaluator-")
                home = os.path.join(private, "home")
                os.mkdir(home, 0o700)
                environment = dict(os.environ)
                environment.update({"HOME": home, "TMPDIR": private, "PYTHONNOUSERSITE": "1"})
            for relative, source in sorted(config.get("protected_inputs", {}).items()):
                _restore(relative, source)
            for relative in [config["metrics_file"], *config.get("analysis_artifacts", [])]:
                output = _inside_workspace(relative)
                if output.is_symlink() or output.exists():
                    if output.is_dir() and not output.is_symlink():
                        _fail("Evaluation output path became a directory: " + relative)
                    output.unlink()
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=environment,
        )
        threads = []
        for index, stream in enumerate((process.stdout, process.stderr)):
            thread = threading.Thread(target=drain, args=(stream, index), daemon=True)
            thread.start()
            threads.append(thread)
        try:
            code = process.wait(
                timeout=max(0.001, config["timeout_seconds"] - (time.monotonic() - started))
            )
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code = 124
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for thread in threads:
            thread.join(timeout=5)
        if code:
            break
    for log in logs:
        log.close()
    raise SystemExit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    main()
