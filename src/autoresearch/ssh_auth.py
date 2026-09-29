"""Transient OpenSSH authentication over a controlling PTY, never a shell."""

from __future__ import annotations

import os
import re
import select
import signal
import subprocess
import sys
import termios
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

# A fresh interpreter establishes the controlling terminal. This avoids preexec_fn,
# which can deadlock when the web server forks from a multithreaded process.
_PTY_EXEC = """import fcntl, os, sys, termios
os.setsid()
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
settings = termios.tcgetattr(0)
settings[3] &= ~(termios.ECHO | termios.ECHONL)
termios.tcsetattr(0, termios.TCSANOW, settings)
os.execvp(sys.argv[1], sys.argv[1:])
"""
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


class AuthenticationSession:
    """Own one master connection; completed authentication keeps its carrier alive."""

    def __init__(
        self,
        argv: list[str],
        ready: Callable[[], bool],
        *,
        timeout: float = 300,
        borrowed: bool = False,
    ) -> None:
        self.id = uuid.uuid4().hex
        self._ready = ready
        self._timeout = timeout
        self._started = time.monotonic()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._termination_lock = threading.Lock()
        self._terminated = False
        self._answers: list[str] = []
        self._output = ""
        self._status = "authenticated" if borrowed else "authenticating"
        self._message = "Existing SSH connection is ready." if borrowed else "Waiting for SSH."
        self._fd: int | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self.borrowed = borrowed
        if borrowed:
            return
        master, slave = os.openpty()
        try:
            settings = termios.tcgetattr(slave)
            settings[3] &= ~(termios.ECHO | termios.ECHONL)
            termios.tcsetattr(slave, termios.TCSANOW, settings)
            # DISPLAY/SSH_ASKPASS must not move authentication out of the app.
            env = {k: v for k, v in os.environ.items() if k not in {"SSH_ASKPASS", "DISPLAY"}}
            env["SSH_ASKPASS_REQUIRE"] = "never"
            self._process = subprocess.Popen(
                [sys.executable, "-c", _PTY_EXEC, *argv],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=env,
                close_fds=True,
            )
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self._fd = master
        self._thread = threading.Thread(target=self._watch, name="ssh-auth", daemon=True)
        self._thread.start()

    def _append(self, data: bytes) -> None:
        with self._lock:
            # After success there are no prompts to display. Discard late terminal
            # echoes so authentication answers can be forgotten immediately.
            if self._status == "authenticating":
                self._output = (self._output + data.decode("utf-8", errors="replace"))[-65536:]

    def _watch(self) -> None:
        assert self._process is not None and self._fd is not None
        while not self._stop.is_set():
            try:
                readable, _, _ = select.select([self._fd], [], [], 0.15)
                if readable:
                    chunk = os.read(self._fd, 8192)
                    if chunk:
                        self._append(chunk)
            except (OSError, ValueError):
                pass
            if self._process.poll() is not None:
                with self._lock:
                    if self._status not in {"cancelled", "expired"}:
                        self._status = "failed"
                        self._message = "SSH connection closed. Sign in again to reconnect."
                self._finish_watch()
                return
            with self._lock:
                authenticating = self._status == "authenticating"
            if authenticating:
                try:
                    ready = self._ready()
                except (OSError, subprocess.SubprocessError):
                    ready = False
                if self._stop.is_set():
                    return
                if ready:
                    with self._lock:
                        # Drain any final terminal echo before discarding answer material.
                        for _ in range(16):
                            try:
                                readable, _, _ = select.select([self._fd], [], [], 0)
                                if not readable:
                                    break
                                self._append(os.read(self._fd, 8192))
                            except (OSError, ValueError):
                                break
                        self._output = self.result()["output"]
                        self._answers.clear()
                        self._status = "authenticated"
                        self._message = "SSH authentication completed."
                elif time.monotonic() - self._started >= self._timeout:
                    with self._lock:
                        self._status = "expired"
                        self._message = "SSH authentication timed out. Start sign-in again."
                    self._finish_watch()
                    return

    def result(self) -> dict[str, Any]:
        with self._lock:
            output = _ANSI.sub("", self._output)
            for answer in sorted(self._answers, key=len, reverse=True):
                if answer:
                    output = output.replace(answer, "[redacted]")
                    # Also conceal a partial echo split across reads/polls.
                    for size in range(min(len(answer) - 1, len(output)), 0, -1):
                        if output.endswith(answer[:size]):
                            output = output[:-size] + "[redacted]"
                            break
            output = "".join(c for c in output if c in "\n\r\t" or c.isprintable())
            return {
                "session_id": self.id,
                "status": self._status,
                "output": output[-32768:],
                "message": self._message,
            }

    def answer(self, answer: str) -> dict[str, Any]:
        if (
            not isinstance(answer, str)
            or len(answer) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in answer)
        ):
            raise ValueError(
                "An authentication answer must be one line without control characters."
            )
        with self._lock:
            if self._status != "authenticating" or self._fd is None:
                raise ValueError("This authentication session is no longer waiting for an answer.")
            self._answers.append(answer)
            # OpenSSH controls its terminal too; enforce non-echo immediately before input.
            settings = termios.tcgetattr(self._fd)
            settings[3] &= ~(termios.ECHO | termios.ECHONL)
            termios.tcsetattr(self._fd, termios.TCSANOW, settings)
            os.write(self._fd, (answer + "\n").encode())
        return self.result()

    def _terminate(self) -> None:
        with self._termination_lock:
            if self._terminated:
                return
            # Never signal a retained PGID again after this attempt: its original
            # processes may have exited even when the OS reported a cleanup error.
            self._terminated = True
            try:
                self._terminate_once()
            except (OSError, subprocess.SubprocessError):
                with self._lock:
                    self._status = "failed"
                    self._message = (
                        "SSH cleanup failed; process termination could not be confirmed."
                    )
                raise

    def _terminate_once(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        # Reap ProxyCommand descendants too, even when the SSH leader exited first.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        process.wait(timeout=3)

    def _finish_terminal(self) -> None:
        self._stop.set()
        try:
            self._terminate()
        except (OSError, subprocess.SubprocessError):
            with self._lock:
                self._status = "failed"
                self._message = "SSH cleanup failed; process termination could not be confirmed."
            raise
        finally:
            with self._lock:
                self._output = self.result()["output"]
                self._answers.clear()
                if self._fd is not None:
                    os.close(self._fd)
                    self._fd = None

    def _finish_watch(self) -> None:
        try:
            self._finish_terminal()
        except (OSError, subprocess.SubprocessError):
            # Background failures are observable through result(), not an unhandled
            # thread exception. Explicit close still propagates its cleanup error.
            pass

    def close(self) -> dict[str, Any]:
        self._stop.set()
        with self._lock:
            if self._status not in {"failed", "expired"}:
                self._status = "cancelled"
                self._message = "SSH authentication cancelled."
        # A borrowed user-owned ControlMaster is never terminated.
        try:
            self._terminate()
        finally:
            if self._thread is not None and self._thread is not threading.current_thread():
                self._thread.join(timeout=5)
            self._finish_terminal()
        return self.result()
