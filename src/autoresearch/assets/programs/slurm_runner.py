"""Trusted standalone Slurm worker with bounded logs and argv-only execution."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import FrameType
from typing import BinaryIO, NoReturn


def main() -> None:
    config = json.loads(Path(sys.argv[1]).read_text())
    limit = config["max_log_bytes"]
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

    def kill(signum: int, frame: FrameType | None) -> NoReturn:
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
    for phase, argv in enumerate(commands):
        if phase:
            metrics = Path(config["metrics_file"])
            if not metrics.resolve().is_relative_to(Path.cwd().resolve()):
                raise RuntimeError("Metrics path escaped workspace")
            if metrics.is_symlink():
                raise RuntimeError("Metrics path became a symlink")
            metrics.unlink(missing_ok=True)
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
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
