"""Bounded argv execution with process-group termination and explicit environment.

This is process control, not a sandbox. A caller must authorize the executable,
arguments, working directory and environment before invoking `run_process`.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import tempfile
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int
    duration: float
    timed_out: bool = False


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    # Also kill descendants if the leader exited but left children alive.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def run_process(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    limit: int,
    input_data: bytes | None = None,
) -> ProcessResult:
    started = time.monotonic()
    stdout = bytearray()
    stderr = bytearray()
    truncated = {"stdout": False, "stderr": False}
    with ExitStack() as resources:
        # An anonymous private file avoids pipe deadlocks when large adapter
        # requests and responses flow simultaneously; it is deleted on close.
        stdin_stream = (
            resources.enter_context(tempfile.TemporaryFile()) if input_data is not None else None
        )
        if stdin_stream is not None and input_data is not None:
            stdin_stream.write(input_data)
            stdin_stream.seek(0)
        process = resources.enter_context(
            subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=stdin_stream if stdin_stream is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        )
        resources.callback(_terminate, process)
        assert process.stdout is not None and process.stderr is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, (stdout, "stdout"))
            selector.register(process.stderr, selectors.EVENT_READ, (stderr, "stderr"))
            timed_out = False
            exited_at: float | None = None
            while selector.get_map():
                if time.monotonic() - started >= timeout:
                    timed_out = True
                    _terminate(process)
                    break
                if process.poll() is not None:
                    exited_at = exited_at or time.monotonic()
                    if time.monotonic() - exited_at > 1:
                        _terminate(process)
                        break
                for key, _ in selector.select(timeout=0.1):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    output, channel = key.data
                    remaining = max(0, limit - len(output))
                    output.extend(data[:remaining])
                    truncated[channel] = truncated[channel] or len(data) > remaining
            try:
                code = process.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate(process)
                code = process.returncode
            if process.poll() is not None:
                _terminate(process)
    out = stdout.decode("utf-8", errors="replace") + (
        "\n[truncated]" if truncated["stdout"] else ""
    )
    err = stderr.decode("utf-8", errors="replace") + (
        "\n[truncated]" if truncated["stderr"] else ""
    )
    return ProcessResult(out, err, code, time.monotonic() - started, timed_out)
