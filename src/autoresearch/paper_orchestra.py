"""Pinned official PaperOrchestra integration, isolated execution and artifact provenance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from .accounting import SubordinateCall
from .catalog import AgentCatalog, load_catalog
from .contracts import Model, ProviderConfig, RunState, Usage
from .memory import optimization_state
from .runtime_support import run_process as _run

if TYPE_CHECKING:
    from .config import ResearchConfig
    from .store import Store

UPSTREAM_URL = "https://github.com/google-research/paper-orchestra.git"
UPSTREAM_REVISION = "ca1b3fa01c2970fc7cda32d16245db38d57b3f56"


class NativePrice(Model):
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)
    request_usd: float = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=12000, ge=256)


class PaperOrchestraConfig(Model):
    checkout_dir: str = ""
    python_executable: str = "python3"
    backend: Literal["docker", "local"] = "docker"
    allow_local: bool = False
    docker_image: str = "scientisttwo-paper-orchestra:pinned"
    template_dir: str = ""  # Empty selects the pinned ICLR 2025 template.
    paperbanana_dir: str = ""
    use_plotting: bool = True
    research_cutoff: str = ""
    # Empty role names use the repository's configured compatible provider.
    writer_model_name: str = ""
    reflection_model_name: str = ""
    plotting_model_name: str = ""
    literature_model_name: str = "gemini-3.1-pro-preview"
    image_model_name: str = "gemini-3-pro-image-preview"
    native_prices: dict[str, NativePrice] = Field(default_factory=dict)
    compatible_models: dict[str, ProviderConfig] = Field(default_factory=dict)
    max_cost_usd: float = Field(default=15, gt=0)
    # Unknown native model prices/usage are charged conservatively per request.
    unpriced_call_usd: float = Field(default=1, gt=0)
    timeout_seconds: int = Field(default=86400, ge=1, le=604800)
    max_reflections: int = Field(default=3, ge=1)
    plotting_max_critic_rounds: int = Field(default=3, ge=1)


class PaperOrchestraError(RuntimeError):
    """Official backend failure. Checkpoints and diagnostics are retained."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    """Replace files without following model-created symlinks or hardlinks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise PaperOrchestraError("Refusing a symlink in a writer output path")
    temporary = path.parent / (".writer-" + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def verify_checkout(path: Path) -> None:
    """Require the audited commit and reject all local tracked/untracked modifications."""
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True, timeout=30
        ).strip()
        changes = subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PaperOrchestraError(
            "PaperOrchestra checkout unavailable; follow docs/paper-orchestra.md"
        ) from exc
    if revision != UPSTREAM_REVISION or changes.strip():
        raise PaperOrchestraError("PaperOrchestra must be a clean checkout of " + UPSTREAM_REVISION)


def materialize_raw_materials(
    state: RunState, target: Path, *, catalog: AgentCatalog | None = None
) -> None:
    """Every attempted experiment, including failures, remains visible to the writer."""
    state = optimization_state(state)
    catalog = catalog or load_catalog()
    role = "revise" if state.stage == "revise" else "draft"
    material_prompts = catalog.definition(role).material_prompts
    if not material_prompts:
        raise PaperOrchestraError("Writer requires declared evidence-reporting prompt artifacts")
    target.mkdir(parents=True, exist_ok=True)
    selected = next((idea for idea in state.ideas if idea.id == state.selected_idea), None)
    if selected is None:
        raise PaperOrchestraError("PaperOrchestra requires a selected research hypothesis")
    idea = f"# {state.title}\n\n{state.objective}\n\n## Selected hypothesis\n"
    idea += json.dumps(selected.model_dump(), indent=2) + "\n\n"
    idea += "## Verified limitations\n" + "\n".join(state.limitations)
    idea += "\n\n## Revision instructions and prior reviews\n" + state.feedback
    idea += "\n" + json.dumps(state.reviews, indent=2)
    if state.manuscript:
        idea += (
            "\n\n## Previous manuscript (revise against new measured evidence)\n" + state.manuscript
        )
    (target / "idea_sparse.md").write_text(idea)
    experiments = [item.model_dump(mode="json") for item in state.experiments]
    (target / "experimental_log.md").write_text(
        "\n\n".join(catalog.text(prompt).strip() for prompt in material_prompts)
        + "\n\n"
        + json.dumps(
            {
                "baseline": state.baseline,
                "experiments": experiments,
                "plans": state.plans,
                "history": state.memory,
                "references": [e.model_dump(mode="json") for e in state.evidence],
            },
            indent=2,
        )
    )
    _write_json(
        target / "instruction-provenance.json",
        {
            "catalog_sha256": catalog.digest,
            "agent_role": role,
            "agent_version": catalog.definition(role).version,
            "material_prompts": {
                prompt: catalog.manifest()["artifacts"][prompt] for prompt in material_prompts
            },
        },
    )
    _write_json(target / "state.json", state.model_dump(mode="json"))
    _write_json(
        target / "evidence_claims.json",
        [
            {
                "experiment_id": exp.id,
                "metric": metric,
                "value": value,
                "status": exp.status,
                "provenance": exp.provenance,
            }
            for exp in state.experiments
            for metric, value in exp.metrics.items()
        ],
    )
    _write_json(target / "references.json", [e.model_dump(mode="json") for e in state.evidence])
    figures = target / "figures"
    figures.mkdir(exist_ok=True)
    _write_json(figures / "info.json", [])
    # Archive selected implementation without mutable links or credentials.
    source = Path(selected.workspace)
    if selected.workspace and source.is_dir():
        archive = target / "selected_implementation"
        archive.mkdir(exist_ok=True)
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if any(p.startswith(".") or p in {"venv", "__pycache__"} for p in relative.parts):
                continue
            if (
                path.is_symlink()
                or not path.is_file()
                or path.suffix
                not in {".py", ".json", ".toml", ".md", ".csv", ".txt", ".yaml", ".yml"}
                or path.stat().st_size > 20_000_000
            ):
                continue
            if re.search(r"(?i)(secret|credential|api.?key)", path.name):
                continue
            dest = archive / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)


def resolve_writer_config(config: ResearchConfig) -> dict[str, Any]:
    options = config.paper_orchestra.model_dump(mode="json")
    for role in ("writer", "reflection", "plotting"):
        key = role + "_model_name"
        if not options[key]:
            alias = "scientisttwo-" + role
            provider = config.role_providers.get("writing_" + role, config.provider)
            options["compatible_models"][alias] = provider.model_dump(mode="json")
            options[key] = alias
    return options


def _command(
    base: Path, upstream: Path, options: dict[str, Any]
) -> tuple[list[str], dict[str, str]]:
    package = Path(__file__).parent.parent
    names = {"GEMINI_API_KEY", "SEMANTIC_SCHOLAR_API_KEY"}
    names.update(p["api_key_env"] for p in options["compatible_models"].values())
    # No ambient proxy, cloud identity, .env, SSH agent or unrelated API credentials.
    env = {name: os.environ[name] for name in names if name in os.environ}
    env.update(
        PATH=os.environ.get("PATH", "/usr/bin:/bin"),
        PYTHONUNBUFFERED="1",
        PYTHONDONTWRITEBYTECODE="1",
        MPLBACKEND="Agg",
    )
    if options["backend"] == "local":
        if not options["allow_local"]:
            raise PaperOrchestraError(
                "Local PaperOrchestra executes generated Python; set allow_local explicitly or use Docker"
            )
        env["PYTHONPATH"] = str(package)
        env["HOME"] = str(base / "home")
        argv = [
            options["python_executable"],
            "-m",
            "autoresearch.paper_orchestra_worker",
            "--job",
            str(base),
            "--upstream",
            str(upstream),
        ]
        return argv, env
    argv = [
        "docker",
        "run",
        "--name",
        "autoresearch-writer-" + base.name,
        "--rm",
        "--init",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        "--memory=8g",
        "--cpus=4",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,size=1g",  # noqa: S108
        "--mount",
        f"type=bind,source={base},target=/job",
        "--mount",
        f"type=bind,source={upstream},target=/upstream,readonly",
        "--mount",
        f"type=bind,source={package},target=/integration,readonly",
        "--env",
        "PYTHONPATH=/integration",
        "--env",
        "HOME=/job/home",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "MPLBACKEND=Agg",
    ]
    for name in sorted(names):
        if name in env:
            argv.extend(["--env", name])
    argv.extend(
        [
            options["docker_image"],
            "python",
            "-m",
            "autoresearch.paper_orchestra_worker",
            "--job",
            "/job",
            "--upstream",
            "/upstream",
        ]
    )
    return argv, env


def _serve_plot_requests(base: Path, options: dict[str, Any]) -> None:
    queue = base / "plot_requests"
    if not queue.exists():
        return
    for request in sorted(queue.glob("*/ready.json")):
        folder = request.parent
        if not re.fullmatch(r"[a-f0-9]{64}", folder.name) or folder.is_symlink():
            raise PaperOrchestraError("Unsafe plot request directory")
        if request.is_symlink() or (folder / "result.json").is_symlink():
            raise PaperOrchestraError("Unsafe plot request/result symlink")
        if (folder / "result.json").exists():
            continue
        workload = folder / "workload"
        if workload.is_symlink():
            raise PaperOrchestraError("Unsafe plot workload symlink")
        workload.mkdir(exist_ok=True)
        code = folder / "code.txt"
        if code.is_symlink():
            raise PaperOrchestraError("Unsafe plot source symlink")
        _atomic_write(workload / "code.txt", code.read_bytes())
        package = Path(__file__).parent.parent
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "MPLBACKEND": "Agg",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(workload),
        }
        container_name = "paper-orchestra-plot-" + uuid.uuid4().hex
        if options["backend"] == "docker":
            argv = [
                "docker",
                "run",
                "--name",
                container_name,
                "--rm",
                "--init",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=64",
                "--memory=2g",
                "--cpus=1",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--tmpfs",
                "/tmp:rw,nosuid,size=256m",  # noqa: S108
                "--mount",
                f"type=bind,source={workload},target=/plot",
                "--mount",
                f"type=bind,source={package},target=/integration,readonly",
                "--env",
                "PYTHONPATH=/integration",
                "--env",
                "HOME=/plot",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                "--workdir",
                "/plot",
                options["docker_image"],
                "python",
                "-m",
                "autoresearch.paper_orchestra_plot",
                "/plot",
            ]
        else:
            env["PYTHONPATH"] = str(package)
            argv = [
                options["python_executable"],
                "-m",
                "autoresearch.paper_orchestra_plot",
                str(workload),
            ]
        try:
            result = _run(argv, cwd=workload, env=env, timeout=120, limit=1_000_000)
            _atomic_write(folder / "stdout.log", result.stdout.encode())
            _atomic_write(folder / "stderr.log", result.stderr.encode())
            _write_json(
                folder / "result.json",
                {
                    "exit_code": None if result.timed_out else result.returncode,
                    "timed_out": result.timed_out,
                    "argv": argv,
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _write_json(folder / "result.json", {"exit_code": None, "error": type(exc).__name__})
        finally:
            if options["backend"] == "docker":
                # Killing the CLI does not stop the container. Remove it before trusting files.
                _run(
                    ["docker", "rm", "--force", container_name],
                    cwd=base,
                    env=env,
                    timeout=15,
                    limit=4096,
                )


def collect_artifacts(store: Store, state: RunState, base: Path) -> list[dict[str, Any]]:
    """Immutable archive includes all stage outputs, logs, sources and diagnostics."""
    records = []
    manifest: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*")):
        if path.is_symlink():
            raise PaperOrchestraError("Writer artifact tree contains a symlink")
        if path.is_file() and not {"home", "paperbanana"}.intersection(
            path.relative_to(base).parts
        ):
            manifest.append(
                {
                    "path": str(path.relative_to(base)),
                    "sha256": digest(path),
                    "bytes": path.stat().st_size,
                }
            )
    stamp = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    with tempfile.TemporaryFile() as handle:
        with tarfile.open(fileobj=handle, mode="w:gz") as archive:
            for item in manifest:
                archive.add(base / item["path"], arcname=item["path"], recursive=False)
        handle.seek(0)
        records.append(
            store.artifact_bytes(
                state.id, "paper_orchestra_bundle", f"paper-orchestra-{stamp}.tar.gz", handle.read()
            )
        )
    records.append(
        store.artifact(
            state.id,
            "paper_orchestra_manifest",
            f"paper-orchestra-{stamp}.json",
            json.dumps(manifest, indent=2),
        )
    )
    for path in (
        base / "final_paper.pdf",
        base / "reflection" / "final_refined_paper.tex",
        base / "reflection" / "references.bib",
    ):
        if path.is_file():
            records.append(
                store.artifact_bytes(
                    state.id,
                    "paper_orchestra_" + path.suffix[1:],
                    f"paper-orchestra-{stamp}-{path.name}",
                    path.read_bytes(),
                )
            )
    return records


def preflight_writer(config: ResearchConfig) -> dict[str, Any]:
    options = resolve_writer_config(config)
    errors: list[str] = []
    upstream = Path(options["checkout_dir"]).expanduser()
    try:
        verify_checkout(upstream)
    except PaperOrchestraError as exc:
        errors.append(str(exc))
    if options["backend"] == "docker" and shutil.which("docker") is None:
        errors.append("Docker executable unavailable; build the documented writer image")
    if options["backend"] == "local" and not options["allow_local"]:
        errors.append("Local generated-code execution requires paper_orchestra.allow_local")
    if not os.environ.get("GEMINI_API_KEY"):
        errors.append(
            "GEMINI_API_KEY required for native grounded literature search and image generation"
        )
    for provider in options["compatible_models"].values():
        if not os.environ.get(provider["api_key_env"]):
            errors.append("Missing credential environment variable " + provider["api_key_env"])
    if options["use_plotting"]:
        refs = Path(options["paperbanana_dir"])
        for task in ("diagram", "plot"):
            if (
                not options["paperbanana_dir"]
                or not (refs / f"data/PaperBananaBench/{task}/ref.json").is_file()
            ):
                errors.append(
                    "Missing official " + task + " reference examples; run paper_orchestra_setup"
                )
    return {
        "ready": not errors,
        "errors": errors,
        "revision": UPSTREAM_REVISION,
        "backend": options["backend"],
        "models": {k: v for k, v in options.items() if k.endswith("_model_name")},
        "unpriced_native_models": [
            name
            for name in (options["literature_model_name"], options["image_model_name"])
            if name not in options["native_prices"]
        ],
    }


def settle_worker_accounting(store: Store, state: RunState, base: Path) -> None:
    """Explicit recovery for pre-versioned receipts after confirming worker termination.

    Retained for historical reservations and their crash/overrun regressions. The
    normal writer lifecycle exclusively uses WriterAccounting; it rejects this
    older receipt shape instead of silently migrating an uncertain active worker.
    """
    path = base / "accounting.json"
    if not path.exists():
        return
    record = json.loads(path.read_text())
    if record.get("status") == "settled":
        return
    previous_ids = set(record["previous_ids"])
    rows = [r for r in _usage_rows(base / "usage.jsonl") if r["id"] not in previous_ids]
    if "usage" not in record:
        record["usage"] = Usage(
            input_tokens=sum(r.get("input_tokens", 0) for r in rows),
            output_tokens=sum(r.get("output_tokens", 0) for r in rows),
            cost_usd=sum(r["cost_usd"] for r in rows),
            estimated=any(r.get("estimated", False) for r in rows),
            latency_seconds=max(0, time.time() - record["started_at"]),
        ).model_dump(mode="json")
        _write_json(path, record)
    # Saving the exact settlement first makes recovery idempotent across a parent crash.
    store.settle(
        record["reservation"],
        Usage.model_validate(record["usage"]),
        subordinate_calls=[SubordinateCall.from_record("paper_orchestra", row) for row in rows],
        stage=state.stage,
    )
    record["status"] = "settled"
    _write_json(path, record)


def _docker_worker_running(base: Path) -> bool:
    """The container owns the work; a disconnected Docker client does not."""
    try:
        done = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                "autoresearch-writer-" + base.name,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PaperOrchestraError("Cannot reconcile the owned writer container") from exc
    if done.returncode == 0 and done.stdout.strip() in {"true", "false"}:
        return done.stdout.strip() == "true"
    if done.returncode != 0 and "No such" in done.stderr:
        return False
    raise PaperOrchestraError("Cannot reconcile the owned writer container")


def _process_group_running(pgid: int) -> bool:
    """Check all group members; zombies cannot issue calls or mutate artifacts."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise PaperOrchestraError("Cannot inspect the previous writer process group") from exc
    try:
        rows = subprocess.run(
            ["ps", "-axo", "pid=,pgid=,stat="],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PaperOrchestraError("Cannot inspect the previous writer process group") from exc
    if rows.returncode or not rows.stdout.strip():
        raise PaperOrchestraError("Cannot inspect the previous writer process group")
    for line in rows.stdout.splitlines():
        fields = line.split()
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            raise PaperOrchestraError("Unexpected process-group inspection response")
        if int(fields[1]) == pgid and not fields[2].startswith("Z"):
            return True
    return False


def _assert_previous_worker_exited(base: Path, options: dict[str, Any]) -> None:
    receipt = base / "supervisor.json"
    if not receipt.exists():
        legacy = base / "accounting.json"
        if legacy.exists() and json.loads(legacy.read_text()).get("schema_version") != 1:
            raise PaperOrchestraError(
                "Legacy writer accounting needs explicit reconciliation before journal recovery"
            )
        return
    process = json.loads(receipt.read_text())
    if options["backend"] == "docker":
        if _docker_worker_running(base):
            raise PaperOrchestraError("Previous writer container is running; resume after it exits")
        return
    pgid = process.get("pgid", process.get("pid"))
    if not isinstance(pgid, int) or isinstance(pgid, bool) or pgid <= 0:
        if process.get("exited") and process.get("pid") is None:
            return  # Popen failed before a process was created.
        raise PaperOrchestraError(
            "Previous writer launch has an uncertain process identity; inspect its supervisor and worker receipts before resuming"
        )
    if _process_group_running(pgid):
        raise PaperOrchestraError(
            "Previous writer process group is still running; resume after it exits"
        )


def _wait_writer_group(pgid: int, process: subprocess.Popen[Any], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        process.poll()  # Reap the owned leader while checking surviving descendants.
        if not _process_group_running(pgid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _stop_writer_process(
    process: subprocess.Popen[Any],
    base: Path,
    options: dict[str, Any],
    *,
    grace_seconds: float = 10,
) -> None:
    if options["backend"] == "docker":
        # Always remove/reconcile the owned container, even if the CLI has exited.
        try:
            stopped = subprocess.run(
                ["docker", "rm", "--force", "autoresearch-writer-" + base.name],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PaperOrchestraError(
                "Cannot stop owned writer container; reservation retained"
            ) from exc
        if stopped.returncode != 0 and "No such" not in stopped.stderr:
            raise PaperOrchestraError("Cannot stop owned writer container; reservation retained")
        if _docker_worker_running(base):
            raise PaperOrchestraError("Owned writer container remains active; reservation retained")
    pgid = process.pid  # start_new_session=True establishes this owned process group.
    if _process_group_running(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if not _wait_writer_group(pgid, process, grace_seconds):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if not _wait_writer_group(pgid, process, 5):
                raise PaperOrchestraError(
                    "Owned writer descendants remain active; reservation retained"
                )
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise PaperOrchestraError(
            "Writer process exit remains uncertain; reservation retained"
        ) from exc


def _recover_writer_journals(base: Path, options: dict[str, Any]) -> None:
    """Repair only interrupted tail writes after verifying that every worker exited."""
    _assert_previous_worker_exited(base, options)
    for name in ("usage.jsonl", "requests.jsonl"):
        path = base / name
        if path.is_symlink():
            raise PaperOrchestraError("Refusing a symlink in a writer journal")
        if not path.exists():
            continue
        raw = path.read_bytes()
        lines = raw.splitlines(keepends=True)
        for index, line in enumerate(lines):
            try:
                json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                if index != len(lines) - 1 or line.endswith(b"\n"):
                    raise PaperOrchestraError(
                        f"Corrupt interior or terminated record in {name}; explicit reconciliation required"
                    ) from exc
                break
        else:
            if not lines or raw.endswith(b"\n"):
                continue
            index = len(lines) - 1  # Complete JSON lost only its final newline.
            line = lines[index]
        digest_value = hashlib.sha256(line).hexdigest()
        archive = base / f"{name}-interrupted-tail-{digest_value}.bin"
        if archive.is_symlink():
            raise PaperOrchestraError("Refusing a symlink in a writer journal archive")
        if archive.exists() and archive.read_bytes() != line:
            raise PaperOrchestraError("Interrupted journal tail archive changed")
        if not archive.exists():
            _atomic_write(archive, line)
        try:
            json.loads(line)
            repaired = raw + b"\n"
        except (json.JSONDecodeError, UnicodeDecodeError):
            repaired = b"".join(lines[:index])
        _atomic_write(path, repaired)


def run_official_writer(
    state: RunState, store: Store, config: ResearchConfig
) -> tuple[str, list[dict[str, Any]]]:
    options = resolve_writer_config(config)
    if not options["checkout_dir"]:
        raise PaperOrchestraError(
            "Configure paper_orchestra.checkout_dir; see docs/paper-orchestra.md. There is no reconstructed writer fallback."
        )
    upstream = Path(options["checkout_dir"]).expanduser().resolve()
    verify_checkout(upstream)
    # Timestamp/state version changes do not invalidate resumable scientific work.
    payload = state.model_dump(
        mode="json", exclude={"version", "created_at", "updated_at", "status", "error"}
    )
    spec_dir = getattr(config, "specification_dir", "")
    catalog = load_catalog(Path(spec_dir) if spec_dir else None)
    fingerprint = hashlib.sha256(
        json.dumps([payload, options, catalog.digest], sort_keys=True).encode()
    ).hexdigest()
    base = store.run_dir(state.id) / "paper_orchestra" / fingerprint[:20]
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    (base / "home").mkdir(exist_ok=True)
    if not (base / "job.json").exists():
        materialize_raw_materials(state, base / "raw_materials", catalog=catalog)
        template = (
            Path(options["template_dir"])
            if options["template_dir"]
            else upstream / "templates/iclr2025"
        )
        for required in (
            "template.tex",
            "guidelines.md",
            "iclr2025_conference.sty",
            "iclr2025_conference.bst",
            "math_commands.tex",
        ):
            if not (template / required).is_file():
                raise PaperOrchestraError(f"Incomplete ICLR template: {required}")
        shutil.copytree(template, base / "template", dirs_exist_ok=True)
        if options["use_plotting"]:
            refs = Path(options["paperbanana_dir"])
            for task in ("plot", "diagram"):
                for relative in (
                    f"data/PaperBananaBench/{task}/ref.json",
                    f"style_guides/neurips2025_{task}_style_guide.md",
                ):
                    if not options["paperbanana_dir"] or not (refs / relative).is_file():
                        raise PaperOrchestraError(
                            "Official plotting reference materials required: paperbanana_dir; see docs/paper-orchestra.md"
                        )
            from .paper_orchestra_setup import verify_plotting_materials

            verify_plotting_materials(refs)
            provenance = []
            for folder in ("data/PaperBananaBench", "style_guides"):
                for path in sorted((refs / folder).rglob("*")):
                    if path.is_symlink():
                        raise PaperOrchestraError("Plotting reference tree contains a symlink")
                    if not path.is_file():
                        continue
                    ref_relative = path.relative_to(refs)
                    destination = base / "paperbanana" / ref_relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
                    provenance.append({"path": str(ref_relative), "sha256": digest(path)})
            from .paper_orchestra_setup import DATA_REVISION, DATA_SHA256, PAPERVIZ_REVISION

            _write_json(
                base / "plotting-reference-provenance.json",
                {
                    "source_revision": PAPERVIZ_REVISION,
                    "dataset_revision": DATA_REVISION,
                    "expected_dataset_archive_sha256": DATA_SHA256,
                    "materialized_files": provenance,
                },
            )
        options["research_cutoff"] = options["research_cutoff"] or state.created_at[:7]
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", options["research_cutoff"]):
            raise PaperOrchestraError("Set paper_orchestra.research_cutoff to YYYY-MM")
        _write_json(
            base / "job.json",
            {
                "schema_version": 1,
                "revision": UPSTREAM_REVISION,
                "fingerprint": fingerprint,
                "options": options,
            },
        )
    from .writer_accounting import WriterAccounting

    accounting = WriterAccounting(base, store, state, fingerprint)
    _recover_writer_journals(base, options)
    accounting.reconcile()
    if (base / "completed.json").exists():
        completion = json.loads((base / "completed.json").read_text())
        if (
            digest(base / "final_paper.pdf") != completion["pdf_sha256"]
            or digest(base / "reflection/final_refined_paper.tex") != completion["source_sha256"]
        ):
            raise PaperOrchestraError("Completed writer artifact integrity check failed")
        collect_artifacts(store, state, base)
        return (base / "reflection/final_refined_paper.tex").read_text(), json.loads(
            (base / "retrieved-evidence.json").read_text()
        )
    usage_path = base / "usage.jsonl"
    previous_ids = {row["id"] for row in _usage_rows(usage_path)}
    attempted = store.usage(state.id).get("model_calls_attempted", store.usage(state.id)["calls"])
    options["max_calls_total"] = len(previous_ids) + max(0, config.budget.max_calls - attempted)
    job = json.loads((base / "job.json").read_text())
    job["options"]["max_calls_total"] = options["max_calls_total"]
    _write_json(base / "job.json", job)
    argv, env = _command(base, upstream, options)
    (base / "failure.json").unlink(missing_ok=True)
    accounting.reserve_remaining(options["max_cost_usd"])
    started = time.monotonic()
    failure = ""
    process: subprocess.Popen[Any] | None = None
    supervisor: dict[str, Any] = {"backend": options["backend"], "pid": None, "exited": False}
    _write_json(base / "supervisor.json", supervisor)
    try:
        with (base / "process.log").open("ab") as log:
            process = subprocess.Popen(
                argv,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=base,
                start_new_session=True,
            )
            supervisor["pid"] = process.pid
            supervisor["pgid"] = process.pid
            _write_json(base / "supervisor.json", supervisor)
            while process.poll() is None:
                if time.monotonic() - started > options["timeout_seconds"]:
                    raise PaperOrchestraError(
                        "Official writer timed out; resume reuses completed stages and API responses"
                    )
                _serve_plot_requests(base, options)
                time.sleep(0.2)
            if process.returncode != 0 or not (base / "completed.json").is_file():
                raise PaperOrchestraError(
                    f"Official writer failed (exit {process.returncode}); inspect versioned process.log and checkpoints"
                )
    except (OSError, PaperOrchestraError) as exc:
        failure = str(exc)
    finally:
        # An error in plotting/supervision must also stop the owned writer before settlement.
        if process is not None:
            _stop_writer_process(process, base, options)
        supervisor["exited"] = True
        _write_json(base / "supervisor.json", supervisor)
        _recover_writer_journals(base, options)
        accounting.reconcile()
        collect_artifacts(store, state, base)
    if failure:
        raise PaperOrchestraError(failure)
    return (base / "reflection/final_refined_paper.tex").read_text(), json.loads(
        (base / "retrieved-evidence.json").read_text()
    )


def _usage_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        latest[row["id"]] = row
    return list(latest.values())


def main() -> None:
    """Install only the audited source revision; never executes downloaded source."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    if args.checkout.exists():
        verify_checkout(args.checkout)
    else:
        subprocess.run(["git", "clone", UPSTREAM_URL, str(args.checkout)], check=True)
        subprocess.run(
            ["git", "-C", str(args.checkout), "checkout", "--detach", UPSTREAM_REVISION], check=True
        )
        verify_checkout(args.checkout)
    print(
        f"Verified PaperOrchestra {UPSTREAM_REVISION}. Follow docs/paper-orchestra.md for runtime setup."
    )


if __name__ == "__main__":
    main()
