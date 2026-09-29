"""Worker adapters around the pinned upstream agents; never a replacement writer.

Run only via paper_orchestra.py. Upstream prompts and agent algorithms are imported
unchanged. Our changes are transport accounting, stage persistence and safe compile.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import importlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .paper_orchestra import (
    UPSTREAM_REVISION,
    PaperOrchestraError,
    _usage_rows,
    _write_json,
    digest,
)

_STAGE: ContextVar[str] = ContextVar("writer_stage", default="")
_OBSERVATION: ContextVar[str] = ContextVar("writer_observation", default="")
_REQUEST_LOCK = threading.RLock()


@contextmanager
def propagated_stage_context() -> Iterator[None]:
    """Carry stage identity through upstream's nested executor pools in this worker."""
    original = ThreadPoolExecutor.submit

    def submit(
        executor: ThreadPoolExecutor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Future[Any]:
        context = copy_context()  # Each submission needs its own concurrently enterable context.
        return original(executor, context.run, fn, *args, **kwargs)

    ThreadPoolExecutor.submit = submit  # type: ignore[method-assign, assignment]
    try:
        yield
    finally:
        ThreadPoolExecutor.submit = original  # type: ignore[method-assign]


def _request_receipt(base: Path, row: dict[str, Any]) -> None:
    with _REQUEST_LOCK, (base / "requests.jsonl").open("a") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def unresolved_requests(base: Path, stage: str | None = None) -> list[dict[str, Any]]:
    """A failure is resolved only by a later completed identical request in its stage."""
    path = base / "requests.jsonl"
    with _REQUEST_LOCK:
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    latest = {row["id"]: (index, row) for index, row in enumerate(rows)}
    successes: dict[tuple[str, str], int] = {}
    for index, row in latest.values():
        if row["status"] == "completed":
            key = (row["stage"], row["request_hash"])
            successes[key] = max(index, successes.get(key, -1))
    return [
        row
        for index, row in latest.values()
        if (stage is None or row["stage"] == stage)
        and row["status"] != "completed"
        and successes.get((row["stage"], row["request_hash"]), -1) < index
    ]


def _validate_legacy_calls(base: Path) -> None:
    # Old failed usage rows cannot safely be assigned to a stage after the fact.
    if any(
        not row.get("observation_id") and row["status"] != "completed"
        for row in _usage_rows(base / "usage.jsonl")
    ):
        raise PaperOrchestraError(
            "Legacy writer has unresolved unscoped calls; explicitly reconcile before resuming"
        )


class CallJournal:
    """Durable reserve-before-send accounting, including crashed/failed API calls."""

    def __init__(self, base: Path, options: dict[str, Any]):
        self.base, self.options = base, options
        self.lock = threading.RLock()
        self.path = base / "usage.jsonl"
        self.cache = base / "api_cache"
        self.cache.mkdir(exist_ok=True)
        self.occurrences: dict[str, int] = {}

    def append(self, row: dict[str, Any]) -> None:
        with self.lock, self.path.open("a") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def invoke(
        self,
        provider: str,
        model: str,
        payload: dict[str, Any],
        request: Callable[[], Any],
        decode: Callable[[dict[str, Any]], Any],
        price: dict[str, Any] | None = None,
    ) -> Any:
        return self.observe(
            provider,
            model,
            payload,
            lambda: self._invoke(provider, model, payload, request, decode, price),
        )

    def observe(
        self, provider: str, model: str, payload: dict[str, Any], action: Callable[[], Any]
    ) -> Any:
        """Record adapter validation and budget refusals as well as submitted requests."""
        if _OBSERVATION.get():
            return action()
        row: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "stage": _STAGE.get(),
            "provider": provider,
            "model": model,
            "status": "started",
            "started_at": time.time(),
        }
        # Serialization failure is itself an observable adapter failure.
        try:
            serialized = json.dumps(payload, sort_keys=True, default=_json_default)
        except (TypeError, ValueError) as exc:
            row.update(
                request_hash=hashlib.sha256(
                    (provider + model + str(type(exc))).encode()
                ).hexdigest(),
                status="failed",
                error_type=type(exc).__name__,
            )
            _request_receipt(self.base, row)
            raise
        row["request_hash"] = hashlib.sha256((provider + model + serialized).encode()).hexdigest()
        _request_receipt(self.base, row)
        token = _OBSERVATION.set(row["id"])
        try:
            result = action()
        except BaseException as exc:
            row.update(status="failed", error_type=type(exc).__name__)
            _request_receipt(self.base, row)
            raise
        else:
            row.update(status="completed")
            _request_receipt(self.base, row)
            return result
        finally:
            _OBSERVATION.reset(token)

    def _invoke(
        self,
        provider: str,
        model: str,
        payload: dict[str, Any],
        request: Callable[[], Any],
        decode: Callable[[dict[str, Any]], Any],
        price: dict[str, Any] | None = None,
    ) -> Any:
        serialized = json.dumps(payload, sort_keys=True, default=_json_default)
        request_key = hashlib.sha256(
            (_STAGE.get() + provider + model + serialized).encode()
        ).hexdigest()
        with self.lock:
            occurrence = self.occurrences.get(request_key, 0)
            self.occurrences[request_key] = occurrence + 1
        key = hashlib.sha256(f"{request_key}:{occurrence}".encode()).hexdigest()
        cache = self.cache / (key + ".json")
        if cache.is_file():
            return decode(json.loads(cache.read_text()))
        count = len(serialized.encode()) + 256
        maximum = self.options["unpriced_call_usd"]
        if price:
            maximum = (
                count * price["input_per_million"]
                + price.get("max_output_tokens", 12000) * price["output_per_million"]
            ) / 1e6 + price.get("request_usd", 0)
        row: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "stage": _STAGE.get(),
            "observation_id": _OBSERVATION.get(),
            "provider": provider,
            "model": model,
            "request_hash": request_key,
            "cache_key": key,
            "status": "reserved",
            "input_tokens": count,
            "output_tokens": price.get("max_output_tokens", 12000) if price else 12000,
            "estimated": True,
            "cost_usd": maximum,
            "started_at": time.time(),
        }
        with self.lock:
            existing = _usage_rows(self.path)
            if len(existing) >= self.options.get("max_calls_total", 2000):
                raise PaperOrchestraError("PaperOrchestra subordinate API call limit exhausted")
            used = sum(r["cost_usd"] for r in existing)
            if used + maximum > self.options["max_cost_usd"]:
                raise PaperOrchestraError("PaperOrchestra subordinate API budget exhausted")
            self.append(row)
        try:
            response = request()
            raw = json.loads(response.model_dump_json())
            usage = raw.get("usage_metadata") or raw.get("usage") or {}
            inputs = usage.get("prompt_token_count", usage.get("prompt_tokens"))
            outputs = usage.get("candidates_token_count", usage.get("completion_tokens"))
            thoughts = usage.get("thoughts_token_count", 0) or 0
            if (
                isinstance(inputs, int)
                and isinstance(outputs, int)
                and inputs >= 0
                and outputs >= 0
            ):
                row.update(input_tokens=inputs, output_tokens=outputs + thoughts)
                if price:
                    row.update(
                        estimated=bool(price.get("conservative", False)),
                        cost_usd=(
                            inputs * price["input_per_million"]
                            + (outputs + thoughts) * price["output_per_million"]
                        )
                        / 1e6
                        + price.get("request_usd", 0),
                    )
            row.update(status="completed", latency_seconds=time.time() - row["started_at"])
            self.append(row)
            if row["cost_usd"] > maximum + 1e-9:
                raise PaperOrchestraError(
                    "Subordinate API exceeded conservative reservation; actual cost recorded"
                )
            _write_json(cache, raw)
            return response
        except Exception as exc:
            if row["status"] != "completed":
                row.update(
                    status="failed",
                    error_type=type(exc).__name__,
                    latency_seconds=time.time() - row["started_at"],
                )
                self.append(row)
            raise


def _json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode()}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Unsupported SDK request object: {type(value).__name__}")


class RedactedStream:
    def __init__(self, stream: Any, secrets: list[str]):
        self.stream, self.secrets = stream, secrets

    def write(self, value: str) -> Any:
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        return self.stream.write(value)

    def flush(self) -> None:
        self.stream.flush()

    def __getattr__(self, key: str) -> Any:
        return getattr(self.stream, key)


def instrument_search(base: Path) -> None:
    """Retain exact successful/error S2 responses before upstream drops their provenance."""
    requests: Any = importlib.import_module("requests")
    original_get = requests.get
    lock = threading.RLock()

    def get(url: str, **kwargs: Any) -> Any:
        if url != "https://api.semanticscholar.org/graph/v1/paper/search":
            return original_get(url, **kwargs)
        params = dict(kwargs.get("params", {}))
        params["fields"] += ",url,externalIds"
        kwargs.update(params=params, allow_redirects=False)
        request = {"url": url, "params": params}
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        cache = base / "search_cache" / (key + ".json")
        if cache.exists():
            raw = json.loads(cache.read_text())
            response = requests.Response()
            response.status_code = raw["status_code"]
            response._content = raw["body"].encode()
            return response
        started = time.time()
        try:
            response = original_get(url, **kwargs)
            record = {
                **request,
                "status_code": response.status_code,
                "body": response.text,
                "retrieved_at": started,
            }
            if response.status_code == 200:
                _write_json(cache, record)
            return response
        except Exception as exc:
            record = {
                **request,
                "status_code": None,
                "error_type": type(exc).__name__,
                "retrieved_at": started,
            }
            raise
        finally:
            with lock, (base / "search-http.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")

    requests.get = get


def export_evidence(base: Path) -> None:
    from datetime import UTC, datetime

    from .contracts import Evidence

    metadata = {}
    for path in (base / "search_cache").glob("*.json"):
        raw = json.loads(path.read_text())
        for paper in json.loads(raw["body"]).get("data", []):
            metadata[paper.get("title", "").casefold()] = (paper, raw)
    evidence = []
    for key, citation in json.loads((base / "literature/citation_map.json").read_text()).items():
        pair = metadata.get(citation["title"].casefold())
        if not pair:
            raise PaperOrchestraError("Citation lost its retrieved Semantic Scholar source")
        paper, raw = pair
        paper_id = paper.get("paperId", "")
        url = paper.get("url") or (
            "https://www.semanticscholar.org/paper/" + paper_id if paper_id else ""
        )
        if not url:
            raise PaperOrchestraError("Citation has no resolvable source identifier")
        evidence.append(
            Evidence(
                id=key,
                title=paper["title"],
                url=url,
                excerpt=paper.get("abstract") or "",
                abstract=paper.get("abstract") or "",
                content_hash=hashlib.sha256(json.dumps(paper, sort_keys=True).encode()).hexdigest(),
                retrieved_at=datetime.fromtimestamp(raw["retrieved_at"], UTC).isoformat(),
                provider="paper-orchestra/semantic-scholar",
                identifiers={
                    "bibtex": key,
                    **{str(k): str(v) for k, v in (paper.get("externalIds") or {}).items() if v},
                },
                published_at=paper.get("publicationDate") or str(paper.get("year") or ""),
                retrieval={
                    "upstream_revision": UPSTREAM_REVISION,
                    "citation_key": key,
                    "search_query": raw["params"]["query"],
                    "raw_source": paper,
                },
            ).model_dump(mode="json")
        )
    if not evidence:
        raise PaperOrchestraError("Official literature search produced no inspectable citations")
    _write_json(base / "retrieved-evidence.json", evidence)


class Transports:
    """Keep native Google search/image capabilities; substitute configured text/VLM models."""

    def __init__(self, journal: CallJournal):
        self.journal = journal
        self.options = journal.options
        self.google: Any = None
        self.openai_clients: dict[str, Any] = {}
        self.native_client: Any = None
        self.openai_factory: Any = None

    def install(self) -> None:
        # Prevent the upstream source checkout from loading a private ambient .env.
        dotenv: Any = importlib.import_module("dotenv")
        dotenv.load_dotenv = lambda *args, **kwargs: False
        genai: Any = importlib.import_module("google.genai")
        openai: Any = importlib.import_module("openai")
        self.native_client, self.openai_factory = genai.Client, openai.OpenAI
        genai.Client = lambda *args, **kwargs: SimpleNamespace(
            models=SimpleNamespace(generate_content=self.gemini)
        )
        openai.OpenAI = lambda *args, **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self.openai))
        )
        # SDK clients in upstream are initialized eagerly, even when that provider is unused.
        # Placeholders initialize only our lazy proxies and are never sent over the network.
        os.environ.setdefault("GEMINI_API_KEY", "scientisttwo-unused-provider")
        os.environ.setdefault("OPENAI_API_KEY", "scientisttwo-unused-provider")

    def _compatible(
        self, alias: str, messages: list[dict[str, Any]], temperature: Any = None
    ) -> Any:
        import httpx

        ChatCompletion = importlib.import_module("openai.types.chat").ChatCompletion
        provider = self.options["compatible_models"][alias]
        key = os.environ.get(provider["api_key_env"], "")
        if not key:
            raise PaperOrchestraError(
                "Missing configured provider credential: " + provider["api_key_env"]
            )
        # Reuse the main transport's validated endpoint/credential policy.
        from .contracts import ProviderConfig
        from .providers import CompatibleProvider

        CompatibleProvider(ProviderConfig.model_validate(provider))
        if alias not in self.openai_clients:
            self.openai_clients[alias] = self.openai_factory(
                api_key=key,
                base_url=provider["base_url"],
                max_retries=0,
                timeout=provider["timeout_seconds"],
                http_client=httpx.Client(trust_env=False),
            )
        payload: dict[str, Any] = {
            "model": provider["model"],
            "messages": messages,
            "max_tokens": provider["max_output_tokens"],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if provider.get("reasoning_effort"):
            payload["reasoning_effort"] = provider["reasoning_effort"]
        price = {
            "input_per_million": max(
                provider["input_per_million"], provider["long_input_per_million"]
            ),
            "output_per_million": max(
                provider["output_per_million"], provider["long_output_per_million"]
            ),
            "max_output_tokens": provider["max_output_tokens"],
            "conservative": True,
        }
        return self.journal.invoke(
            provider["name"],
            provider["model"],
            payload,
            lambda: self.openai_clients[alias].chat.completions.create(**payload),
            ChatCompletion.model_validate,
            price,
        )

    def openai(self, **kwargs: Any) -> Any:
        return self.journal.observe(
            "openai", str(kwargs.get("model", "")), kwargs, lambda: self._openai(**kwargs)
        )

    def _openai(self, **kwargs: Any) -> Any:
        model = kwargs["model"]
        if model not in self.options["compatible_models"]:
            raise PaperOrchestraError(
                "Native OpenAI models require an explicit compatible_models entry with pricing"
            )
        return self._compatible(model, kwargs["messages"], kwargs.get("temperature"))

    def gemini(self, **kwargs: Any) -> Any:
        return self.journal.observe(
            "google", str(kwargs.get("model", "")), kwargs, lambda: self._gemini(**kwargs)
        )

    def _gemini(self, **kwargs: Any) -> Any:
        types = importlib.import_module("google.genai.types")
        model = kwargs["model"]
        configs = kwargs.get("config") or {}
        if hasattr(configs, "model_dump"):
            configs = configs.model_dump(exclude_none=True)
        if model in self.options["compatible_models"]:
            if configs.get("tools") or configs.get("response_modalities"):
                raise PaperOrchestraError(
                    "Google grounded search/image generation requires a native capable model; substitutions cannot drop tools"
                )
            messages: list[dict[str, Any]] = []
            if configs.get("system_instruction"):
                messages.append({"role": "system", "content": str(configs["system_instruction"])})
            contents = kwargs["contents"]
            if not isinstance(contents, list):
                contents = [contents]
            parts: list[dict[str, Any]] = []
            for item in contents:
                if isinstance(item, str):
                    parts.append({"type": "text", "text": item})
                else:
                    item_parts = getattr(item, "parts", None) or [item]
                    for part in item_parts:
                        if getattr(part, "text", None):
                            parts.append({"type": "text", "text": part.text})
                        elif getattr(part, "inline_data", None):
                            data = part.inline_data
                            if data.mime_type == "application/pdf":
                                # Preserve visual review: render every PDF page, never silently text-only.
                                fitz = importlib.import_module("fitz")
                                with fitz.open(stream=data.data, filetype="pdf") as pdf:
                                    for page in pdf:
                                        image = page.get_pixmap(matrix=fitz.Matrix(1, 1)).tobytes(
                                            "png"
                                        )
                                        parts.append(
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": "data:image/png;base64,"
                                                    + base64.b64encode(image).decode()
                                                },
                                            }
                                        )
                            elif data.mime_type.startswith("image/"):
                                parts.append(
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": "data:"
                                            + data.mime_type
                                            + ";base64,"
                                            + base64.b64encode(data.data).decode()
                                        },
                                    }
                                )
                            else:
                                raise PaperOrchestraError(
                                    "Unsupported multimodal content; select native Gemini"
                                )
                        else:
                            raise PaperOrchestraError(
                                "Unsupported upstream content part; refusing to discard it"
                            )
            messages.append({"role": "user", "content": parts})
            response = self._compatible(model, messages, configs.get("temperature"))
            if response.choices[0].finish_reason == "length":
                raise PaperOrchestraError("Writer model response was truncated")
            return SimpleNamespace(text=response.choices[0].message.content)
        key = os.environ.get("GEMINI_API_KEY", "")
        if key == "scientisttwo-unused-provider" or not key:
            raise PaperOrchestraError(
                "GEMINI_API_KEY is required for native Google-grounded literature/image workflows"
            )
        if self.google is None:
            self.google = self.native_client(
                api_key=key, http_options=types.HttpOptions(timeout=180000)
            )
        price = self.options["native_prices"].get(model)
        configs["max_output_tokens"] = (price or {}).get("max_output_tokens", 12000)
        kwargs["config"] = types.GenerateContentConfig(**configs)
        return self.journal.invoke(
            "google",
            model,
            kwargs,
            lambda: self.google.models.generate_content(**kwargs),
            types.GenerateContentResponse.model_validate,
            price,
        )


class StageJournal:
    def __init__(self, base: Path):
        self.base = base
        self.path = base / "checkpoint.json"
        self.data = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"schema_version": 1, "stages": {}}
        )
        if self.data.get("schema_version") != 1:
            raise PaperOrchestraError("Unsupported writer checkpoint schema")
        self.lock = threading.RLock()

    def run(self, name: str, action: Callable[[], Any], files: list[Path]) -> Any:
        _validate_legacy_calls(self.base)
        with self.lock:
            old = self.data["stages"].get(name)
            if old and unresolved_requests(self.base, name):
                dependents = {
                    "outline": {"literature", "plotting", "sections", "reflection"},
                    "literature": {"sections", "reflection"},
                    "plotting": {"sections", "reflection"},
                    "sections": {"reflection"},
                }
                removed = {
                    key: self.data["stages"].pop(key)
                    for key in {name} | dependents.get(name, set())
                    if key in self.data["stages"]
                }
                with (self.base / "checkpoint-invalidations.jsonl").open("a") as stream:
                    stream.write(
                        json.dumps({"reason": "unresolved requests", "stages": removed}) + "\n"
                    )
                _write_json(self.path, self.data)
                old = None
        if old:
            for relative, expected in old["artifacts"].items():
                path = self.base / relative
                if not path.is_file() or digest(path) != expected:
                    raise PaperOrchestraError("Checkpoint artifact changed: " + relative)
            return old["result"]
        token = _STAGE.set(name)
        try:
            result = action()
        finally:
            _STAGE.reset(token)
        if unresolved_requests(self.base, name):
            raise PaperOrchestraError("Official " + name + " has unresolved transport requests")
        for path in files:
            if not path.is_file():
                raise PaperOrchestraError(f"Official {name} did not produce {path.name}")
        with self.lock:
            self.data["stages"][name] = {
                "result": result,
                "artifacts": {str(p.relative_to(self.base)): digest(p) for p in files},
            }
            _write_json(self.path, self.data)
        return result


def strict_compile(base: Path) -> Callable[..., None]:
    """The released compiler accepts nonzero exit codes; this adapter fails closed."""
    lock = threading.RLock()

    def compile_latex(
        cwd: str, pdf_file: str, texfile_name: str = "template", timeout: int = 120
    ) -> None:
        folder = Path(cwd).resolve()
        if not folder.is_relative_to(base.resolve()) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+", texfile_name
        ):
            raise PaperOrchestraError("Unsafe LaTeX compile location/name")
        source_pdf = folder / (texfile_name + ".pdf")
        source_pdf.unlink(missing_ok=True)
        commands = [
            [
                "pdflatex",
                "-no-shell-escape",
                "-interaction=nonstopmode",
                "-halt-on-error",
                texfile_name + ".tex",
            ],
            ["bibtex", texfile_name],
            [
                "pdflatex",
                "-no-shell-escape",
                "-interaction=nonstopmode",
                "-halt-on-error",
                texfile_name + ".tex",
            ],
            [
                "pdflatex",
                "-no-shell-escape",
                "-interaction=nonstopmode",
                "-halt-on-error",
                texfile_name + ".tex",
            ],
        ]
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(base / "home"),
            "openin_any": "p",
            "openout_any": "p",
        }
        for command in commands:
            try:
                result = subprocess.run(
                    command, cwd=folder, env=env, capture_output=True, text=True, timeout=timeout
                )
                record = {
                    "argv": command,
                    "cwd": str(folder.relative_to(base)),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            except (OSError, subprocess.TimeoutExpired) as exc:
                record = {
                    "argv": command,
                    "cwd": str(folder.relative_to(base)),
                    "exit_code": None,
                    "error": type(exc).__name__,
                }
            with lock, (base / "compile-diagnostics.jsonl").open("a") as log:
                log.write(json.dumps(record) + "\n")
            if record["exit_code"] != 0:
                source_pdf.unlink(missing_ok=True)
                raise PaperOrchestraError("LaTeX compile failed; inspect compile-diagnostics.jsonl")
        if not source_pdf.is_file() or not source_pdf.read_bytes().startswith(b"%PDF-"):
            raise PaperOrchestraError("Compiler did not produce a PDF")
        if source_pdf.resolve() != Path(pdf_file).resolve():
            shutil.copyfile(source_pdf, pdf_file)

    return compile_latex


def isolated_plot(base: Path) -> Callable[[str], str]:
    def plot(code: str) -> str:
        key = hashlib.sha256(code.encode()).hexdigest()
        folder = base / "plot_requests" / key
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "code.txt").write_text(code)
        _write_json(folder / "ready.json", {"code_sha256": key})
        started = time.monotonic()
        while not (folder / "result.json").is_file():
            if time.monotonic() - started > 900:
                raise PaperOrchestraError("Isolated plotting executor did not respond")
            time.sleep(0.2)
        if (folder / "result.json").is_symlink():
            raise PaperOrchestraError("Plot executor result cannot be a symlink")
        result = json.loads((folder / "result.json").read_text())
        image = folder / "workload/image.jpg"
        if (
            result["exit_code"] != 0
            or not image.is_file()
            or image.is_symlink()
            or image.stat().st_size > 20_000_000
        ):
            raise PaperOrchestraError("Generated plot command failed; inspect versioned plot logs")
        return base64.b64encode(image.read_bytes()).decode()

    return plot


def execute(base: Path, upstream: Path) -> None:
    """An orphan worker retains exclusive ownership until it has stopped spending."""
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PaperOrchestraError("Another writer worker owns this job") from exc
        status = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_at": time.time(),
            "status": "running",
        }
        _write_json(base / "worker-status.json", status)
        try:
            with propagated_stage_context():
                _execute(base, upstream)
        except BaseException as exc:
            status.update(status="failed", error_type=type(exc).__name__, ended_at=time.time())
            _write_json(base / "worker-status.json", status)
            raise
        else:
            status.update(status="completed", ended_at=time.time())
            _write_json(base / "worker-status.json", status)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _execute(base: Path, upstream: Path) -> None:
    job = json.loads((base / "job.json").read_text())
    if job.get("schema_version") != 1 or job.get("revision") != UPSTREAM_REVISION:
        raise PaperOrchestraError("Invalid worker input schema/upstream revision")
    options = job["options"]
    sys.pycache_prefix = str(base / "home/pycache")
    sys.path.insert(0, str(upstream))
    credential_names = {"GEMINI_API_KEY", "SEMANTIC_SCHOLAR_API_KEY"} | {
        p["api_key_env"] for p in options["compatible_models"].values()
    }
    secrets = [
        value for key, value in os.environ.items() if key in credential_names and len(value) > 4
    ]
    sys.stdout = RedactedStream(sys.stdout, secrets)
    sys.stderr = RedactedStream(sys.stderr, secrets)
    instrument_search(base)
    transports = Transports(CallJournal(base, options))
    transports.install()
    pdf_utils: Any = importlib.import_module("utils.pdf_utils")
    pdf_utils.compile_latex = strict_compile(base)
    outline_cls = importlib.import_module("methods.agents.outline_agent").OutlineAgent
    literature_cls = importlib.import_module(
        "methods.agents.literature_review_agent"
    ).HybridLiteratureAgent
    sections_cls = importlib.import_module(
        "methods.agents.section_writing_agent"
    ).SectionWritingAgent
    reflection_cls = importlib.import_module(
        "methods.agents.content_refinement_agent"
    ).ContentRefinementAgent
    journal = StageJournal(base)
    materials, template = base / "raw_materials", base / "template"
    idea, log = str(materials / "idea_sparse.md"), str(materials / "experimental_log.md")
    guidelines, tex_template = str(template / "guidelines.md"), str(template / "template.tex")
    outline = base / "outline.json"
    journal.run(
        "outline",
        lambda: outline_cls(
            model_name=options["writer_model_name"], cutoff_date=options["research_cutoff"]
        ).run(
            idea_file=idea,
            experimental_log_file=log,
            latex_template_file=tex_template,
            conference_guidelines_file=guidelines,
            output_filepath=str(outline),
        ),
        [outline],
    )
    literature_dir = base / "literature"

    def literature() -> None:
        literature_cls(
            idea_path=idea,
            experimental_log_path=log,
            latex_template_path=tex_template,
            conference_guidelines_path=guidelines,
            output_dir=str(literature_dir),
            model_name=options["literature_model_name"],
            max_workers=3,
        ).run(outline_path=str(outline), cutoff_date=options["research_cutoff"])

    def plotting() -> Any:
        utils: Any = importlib.import_module("utils.paper_banana_utils")
        utils.PB_DIR = str(base / "paperbanana")
        utils.execute_plot_code_worker = isolated_plot(base)
        for plan in json.loads(outline.read_text()).get("plotting_plan", []):
            if not re.fullmatch(r"[A-Za-z0-9 _.-]+", plan.get("figure_id", "")):
                raise PaperOrchestraError("Unsafe figure identifier from outline")
        cls = importlib.import_module("methods.agents.plotting_agent").PlottingAgent
        results = cls(
            model_name=options["plotting_model_name"],
            image_model_name=options["image_model_name"],
            max_critic_rounds=options["plotting_max_critic_rounds"],
        ).run(
            outline_json_path=str(outline),
            raw_materials_dir=str(materials),
            output_filepath=str(base / "plotting_results.json"),
        )
        plans = json.loads(outline.read_text()).get("plotting_plan", [])
        if len(results) != len(plans) or any(not r.get("image_path") for r in results):
            raise PaperOrchestraError("Official plotting agent omitted or failed requested figures")
        return results

    with ThreadPoolExecutor(max_workers=2) as pool:
        lit = pool.submit(
            journal.run,
            "literature",
            literature,
            [
                literature_dir / name
                for name in (
                    "outline_v1.json",
                    "updated_template.tex",
                    "references.bib",
                    "citation_map.json",
                )
            ],
        )
        plot = (
            pool.submit(journal.run, "plotting", plotting, [base / "plotting_results.json"])
            if options["use_plotting"]
            else None
        )
        lit.result()
        export_evidence(base)
        plots = plot.result() if plot else []
    writing = base / "writing"
    raw_draft = writing / "raw_draft_paper.tex"

    def sections() -> None:
        shutil.copytree(template, writing, dirs_exist_ok=True)
        shutil.copyfile(literature_dir / "updated_template.tex", writing / "template.tex")
        shutil.copyfile(literature_dir / "references.bib", writing / "references.bib")
        figures = writing / "figures"
        figures.mkdir(exist_ok=True)
        info = []
        for figure in plots:
            relative = Path(figure["image_path"])
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "figures":
                raise PaperOrchestraError("Unsafe generated figure path")
            shutil.copyfile(base / relative, writing / relative)
            info.append({"name": relative.name, "caption": figure.get("caption", "")})
        if not options["use_plotting"]:
            shutil.copytree(materials / "figures", figures, dirs_exist_ok=True)
        else:
            _write_json(figures / "info.json", info)
        sections_cls(
            outline_path=str(literature_dir / "outline_v1.json"),
            template_path=str(writing / "template.tex"),
            idea_path=idea,
            experimental_log_path=log,
            citation_map_path=str(literature_dir / "citation_map.json"),
            figures_info_path=str(figures / "info.json"),
            guidelines_path=guidelines,
            model_name=options["writer_model_name"],
        ).run(output_path=str(raw_draft))

    journal.run("sections", sections, [raw_draft])
    reflection = base / "reflection"

    def reflect() -> None:
        shutil.copytree(writing, reflection, dirs_exist_ok=True)
        pdf = reflection_cls(
            experimental_log_path=log,
            citation_map_path=str(literature_dir / "citation_map.json"),
            guidelines_path=guidelines,
            model_name=options["reflection_model_name"],
            max_reflections=options["max_reflections"],
            work_dir=str(reflection),
        ).run(texfile_path=str(raw_draft))
        if not pdf or not Path(pdf).is_file():
            raise PaperOrchestraError("Official reflection did not produce a valid PDF")
        # Final upstream PDF can be an earlier candidate: recompile final source to verify exact source/PDF agreement.
        pdf_utils.compile_latex(
            str(reflection), str(base / "final_paper.pdf"), "final_refined_paper"
        )

    journal.run(
        "reflection", reflect, [reflection / "final_refined_paper.tex", base / "final_paper.pdf"]
    )
    _validate_legacy_calls(base)
    if unresolved_requests(base):
        raise PaperOrchestraError(
            "Upstream swallowed unresolved API failures; inspect requests.jsonl"
        )
    _write_json(
        base / "completed.json",
        {
            "schema_version": 1,
            "revision": UPSTREAM_REVISION,
            "pdf_sha256": digest(base / "final_paper.pdf"),
            "source_sha256": digest(reflection / "final_refined_paper.tex"),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    try:
        execute(args.job.resolve(), args.upstream.resolve())
    except Exception as exc:
        _write_json(args.job / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


if __name__ == "__main__":
    main()
