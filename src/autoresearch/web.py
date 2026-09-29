"""Loopback-only research console with authenticated, checkpoint-based controls.

The console deliberately has no public bind option. Put a real authenticated gateway
in front of a separate service if remote collaboration is needed; an SSH tunnel is
the recommended way to inspect a cluster-side console.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .config import ResearchConfig
from .contracts import Stage
from .engine import Engine
from .fidelity import load_matrix
from .privacy import redact
from .setup import preflight, validate_live_config
from .store import Store

MAX_BODY_BYTES = 64 * 1024
STATIC_DIR = Path(__file__).parent / "static"


class ResearchServer(ThreadingHTTPServer):
    """One in-process worker per run; the engine additionally owns a durable lease."""

    daemon_threads = True

    def __init__(
        self,
        store: Store,
        config: ResearchConfig | None = None,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("The research console must bind to loopback (127.0.0.1 or localhost)")
        self.store = store
        self.config = config
        self.token = secrets.token_urlsafe(32)
        self.workers: dict[str, threading.Thread] = {}
        self.worker_errors: dict[str, str] = {}
        self.worker_lock = threading.Lock()
        super().__init__((host, port), ResearchHandler)
        actual_port = self.server_address[1]
        self.authorities = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
        self.origins = {f"http://{authority}" for authority in self.authorities}

    def working(self, run_id: str) -> bool:
        with self.worker_lock:
            worker = self.workers.get(run_id)
            return worker is not None and worker.is_alive()

    def start_run(self, run_id: str, steps: int | None = None, resume: bool = False) -> None:
        # Resolve the run before accepting a job so nonexistent IDs produce a 404.
        self.store.get_run(run_id)
        config = self.store.get_config(run_id)
        config.project.source_dir = str(self.store.run_dir(run_id) / "source")
        validate_live_config(config)
        with self.worker_lock:
            existing = self.workers.get(run_id)
            if existing is not None and existing.is_alive():
                raise RuntimeError("This run already has an active worker")
            self.worker_errors.pop(run_id, None)
            if resume:
                Engine(self.store).resume(run_id)

            def execute() -> None:
                try:
                    Engine(self.store).run(run_id, max_steps=steps)
                except Exception as exc:  # Persist the worker failure for the local UI.
                    with self.worker_lock:
                        self.worker_errors[run_id] = str(redact(f"{type(exc).__name__}: {exc}"))

            worker = threading.Thread(target=execute, name=f"research-{run_id}", daemon=True)
            self.workers[run_id] = worker
            worker.start()


class ResearchHandler(BaseHTTPRequestHandler):
    server: ResearchServer
    protocol_version = "HTTP/1.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format: str, *args: Any) -> None:
        # URLs, query strings, prompts, and credentials must not become access logs.
        return

    def _send(
        self,
        status: int,
        value: Any,
        content_type: str = "application/json",
        filename: str | None = None,
    ) -> None:
        payload = (
            json.dumps(value, ensure_ascii=False).encode("utf-8")
            if content_type == "application/json"
            else value
        )
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        if filename is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def _guard(self, authenticated: bool = True) -> bool:
        if len(self.headers.get_all("Host", [])) != 1:
            self._send(HTTPStatus.FORBIDDEN, {"error": "Invalid Host header"})
            return False
        if self.headers.get("Host", "").lower() not in self.server.authorities:
            self._send(HTTPStatus.FORBIDDEN, {"error": "Only the local console host is allowed"})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.server.origins:
            self._send(HTTPStatus.FORBIDDEN, {"error": "Cross-origin requests are not allowed"})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self._send(HTTPStatus.FORBIDDEN, {"error": "Cross-site requests are not allowed"})
            return False
        if authenticated:
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {self.server.token}".encode()):
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "Console session token required"})
                return False
        return True

    def _body(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding is not supported")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise ValueError("One Content-Length header is required")
        length = int(lengths[0])
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("Request body exceeds the 64 KiB limit")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        return body

    @staticmethod
    def _text(body: dict[str, Any], key: str, maximum: int) -> str:
        value = body.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f"{key} must be nonempty text of at most {maximum} characters")
        return value.strip()

    @staticmethod
    def _parts(path: str) -> list[str]:
        parts = path.strip("/").split("/")
        # Never decode path components or allow caller-controlled filesystem paths.
        if any(part in {".", ".."} or "%" in part or "\\" in part for part in parts):
            raise ValueError("Invalid API path")
        return parts

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        public = path in {"/", "/index.html", "/app.js", "/style.css", "/api/bootstrap"}
        if not self._guard(authenticated=not public):
            return
        try:
            assets = {
                "/": ("index.html", "text/html"),
                "/index.html": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if path in assets:
                filename, mime = assets[path]
                self._send(200, (STATIC_DIR / filename).read_bytes(), mime)
                return
            if path == "/api/bootstrap":
                self._send(200, {"token": self.server.token, "stages": [s.value for s in Stage]})
                return
            if path == "/api/config":
                defaults = self.server.config or ResearchConfig()
                self._send(
                    200,
                    {
                        "config": _public_config(defaults.model_dump(mode="json")),
                        "readiness": preflight(defaults),
                    },
                )
                return
            if path == "/api/runs":
                runs = self.server.store.list_runs()
                for summary in runs:
                    if self.server.working(summary["id"]):
                        summary["status"] = (
                            "pausing" if self.server.store.is_paused(summary["id"]) else "running"
                        )
                self._send(200, {"runs": runs})
                return
            parts = self._parts(path)
            if len(parts) not in {3, 4, 5} or parts[:2] != ["api", "runs"]:
                self._send(404, {"error": "Unknown endpoint"})
                return
            run_id = parts[2]
            run = self.server.store.get_run(run_id)
            if len(parts) == 3:
                run_config = self.server.store.get_config(run_id)
                config = run_config.model_dump(mode="json")
                snapshot_config = run_config.model_copy(deep=True)
                snapshot_config.project.source_dir = str(
                    self.server.store.run_dir(run_id) / "source"
                )
                self._send(
                    200,
                    {
                        "run": run.model_dump(mode="json"),
                        "config": _public_config(config),
                        "usage": self.server.store.usage(run_id),
                        "artifacts": self.server.store.artifacts(run_id),
                        "working": self.server.working(run_id),
                        "paused": self.server.store.is_paused(run_id),
                        "worker_error": self.server.worker_errors.get(run_id),
                        "readiness": preflight(snapshot_config),
                        "fidelity": load_matrix(),
                    },
                )
            elif len(parts) == 4 and parts[3] == "events":
                query = parse_qs(urlsplit(self.path).query)
                after = int(query.get("after", ["0"])[0])
                if after < 0:
                    raise ValueError("after must be a nonnegative event ID")
                self._send(200, {"events": self.server.store.events(run_id, after=after)})
            elif len(parts) == 5 and parts[3] == "artifacts":
                artifact = next(
                    (a for a in self.server.store.artifacts(run_id) if a["id"] == parts[4]), None
                )
                if artifact is None:
                    raise FileNotFoundError("Unknown artifact")
                root = self.server.store.run_dir(run_id)
                folder = root / "artifacts"
                target = root / artifact["path"]
                if (
                    folder.is_symlink()
                    or target.is_symlink()
                    or not target.resolve().is_relative_to(folder.resolve())
                ):
                    raise ValueError("Artifact path is not inside this run's artifact directory")
                if not target.is_file():
                    raise FileNotFoundError("Artifact not available")
                if target.stat().st_size > 16 * 1024 * 1024:
                    raise ValueError(
                        "Artifact exceeds the 16 MiB browser download limit; inspect it locally"
                    )
                self._send(
                    200,
                    target.read_bytes(),
                    "application/pdf" if target.suffix.lower() == ".pdf" else "application/octet-stream",
                    filename=target.name,
                )
            else:
                self._send(404, {"error": "Unknown endpoint"})
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard():
            return
        try:
            body = self._body()
            parts = self._parts(urlsplit(self.path).path)
            if parts == ["api", "preflight"]:
                config = self._configuration(body)
                self._send(200, preflight(config, probe_runtime=True))
                return
            if parts == ["api", "runs"]:
                title = self._text(body, "title", 200)
                objective = self._text(body, "objective", 20000)
                demo = body.get("demo", False)
                if not isinstance(demo, bool):
                    raise ValueError("demo must be a boolean")
                config = self._configuration(body)
                config.mode = "demo" if demo else "live"
                readiness = preflight(config, probe_runtime=True)
                if not readiness["ready"]:
                    self._send(
                        400,
                        {
                            "error": "Complete the setup checks before creating live research.",
                            "readiness": readiness,
                        },
                    )
                    return
                run = Engine(self.server.store, config).create(title, objective, demo=demo)
                self._send(201, {"run": run.model_dump(mode="json")})
                return
            if len(parts) != 4 or parts[:2] != ["api", "runs"]:
                self._send(404, {"error": "Unknown endpoint"})
                return
            run_id, action = parts[2:]
            self.server.store.get_run(run_id)
            if action in {"run", "resume"}:
                steps = body.get("steps")
                if steps is not None and (type(steps) is not int or steps < 1 or steps > 10000):
                    raise ValueError("steps must be an integer between 1 and 10000")
                self.server.start_run(run_id, steps, resume=action == "resume")
                self._send(202, {"accepted": True})
            elif action == "pause":
                Engine(self.server.store).pause(run_id)
                self._send(202, {"accepted": True, "message": "Pause requested at checkpoint"})
            elif action == "cancel-experiment":
                if self.server.working(run_id):
                    raise RuntimeError(
                        "Pause the run and wait for its checkpoint before cancelling the Slurm experiment"
                    )
                state = Engine(self.server.store).cancel_experiment(run_id)
                self._send(200, {"run": state.model_dump(mode="json")})
            elif action == "intervene":
                if self.server.working(run_id):
                    raise RuntimeError(
                        "Pause the run and wait for its checkpoint before intervening"
                    )
                note = self._text(body, "note", 20000)
                stage = body.get("stage")
                if stage is not None and stage not in {s.value for s in Stage}:
                    raise ValueError("Unknown research stage")
                state = Engine(self.server.store).intervene(run_id, note=note, stage=stage)
                self._send(200, {"run": state.model_dump(mode="json")})
            elif action == "budget":
                if self.server.working(run_id):
                    raise RuntimeError(
                        "Pause the run and wait for its checkpoint before updating the budget"
                    )
                allowed = {"usd", "max_calls", "max_experiments", "wall_seconds"}
                if not body or not set(body).issubset(allowed):
                    raise ValueError(
                        "Provide one or more budget limits: usd, max_calls, max_experiments, wall_seconds"
                    )
                updated = self.server.store.update_budget(run_id, **body)
                self._send(200, {"budget": updated.budget.model_dump(mode="json")})
            else:
                self._send(404, {"error": "Unknown action"})
        except Exception as exc:
            self._error(exc)

    def do_OPTIONS(self) -> None:  # noqa: N802
        # No CORS opt-in: a website cannot use the console as a local API.
        if self._guard(authenticated=False):
            self._send(405, {"error": "Cross-origin access is not supported"})

    def _configuration(self, body: dict[str, Any]) -> ResearchConfig:
        if "config" not in body:
            return (self.server.config or ResearchConfig()).model_copy(deep=True)
        if not isinstance(body["config"], dict):
            raise ValueError("config must be a configuration object")
        return ResearchConfig.model_validate(body["config"])

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, (FileNotFoundError, KeyError)):
            self._send(404, {"error": "Research run or artifact not found"})
        elif isinstance(exc, (ValueError, TypeError)):
            self._send(400, {"error": redact(str(exc))})
        elif isinstance(exc, RuntimeError):
            self._send(409, {"error": redact(str(exc))})
        else:
            self._send(500, {"error": f"Console operation failed ({type(exc).__name__})"})


def _public_config(value: Any) -> Any:
    """Local authenticated settings remain editable, including source paths.

    Never substitute credential values or expose literal tokens in free text.
    Trace/export redaction still hides home directory names by default.
    """
    return redact(value, preserve_paths=True)


def serve(store: Store, config: ResearchConfig | None = None, port: int = 8765) -> None:
    server = ResearchServer(store, config=config, port=port)
    print(f"Research console: http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nConsole stopped. Runs resume from their last completed checkpoint.", flush=True)
    finally:
        server.server_close()
