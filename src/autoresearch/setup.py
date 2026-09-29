"""Local prerequisite checks shared by the terminal and browser setup forms.

Checks do not call models, submit jobs, pull images, or run project commands.
A ready result is not a claim that a benchmark or remote model has been validated.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from .config import ResearchConfig
from .execution import ExecutionError, Executor
from .providers import CompatibleProvider, ProviderError
from .source_policy import source_is_excluded


class Check(TypedDict):
    name: str
    status: Literal["ok", "error", "warning"]
    message: str


class Readiness(TypedDict):
    ready: bool
    checks: list[Check]


def preflight(config: ResearchConfig, *, probe_runtime: bool = False) -> Readiness:
    checks: list[Check] = []

    def add(name: str, status: Literal["ok", "error", "warning"], message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})

    try:
        from .behavior import describe

        describe(config)
        add(
            "ai-specifications",
            "ok",
            "Agent, prompt, tool, model and workflow contracts are valid.",
        )
    except (ValueError, OSError) as exc:
        add("ai-specifications", "error", str(exc))

    if config.mode == "demo":
        add("mode", "ok", "Offline demo: scripted agents and synthetic regression; no API calls.")
        return {"ready": not any(check["status"] == "error" for check in checks), "checks": checks}

    providers = {
        "default": config.provider,
        **{f"role:{name}": provider for name, provider in config.role_providers.items()},
    }
    for role, panel in config.role_panels.items():
        providers.update(
            {f"panel:{role}:{index}": provider for index, provider in enumerate(panel)}
        )
    if config.heldout_provider is not None:
        providers["heldout"] = config.heldout_provider
    if config.cheap_provider is not None:
        providers["cheap"] = config.cheap_provider
    if config.frontier_provider is not None:
        providers["frontier"] = config.frontier_provider
    for role, provider in providers.items():
        name = f"provider:{role}"
        try:
            CompatibleProvider(provider)
        except ProviderError as exc:
            add(name, "error", str(exc))
            continue
        local = urlsplit(provider.base_url).hostname in {"localhost", "127.0.0.1", "::1"}
        key = os.environ.get(provider.api_key_env, "")
        if not provider.model.strip():
            add(name, "error", "Set a model identifier.")
        elif not key and not local:
            add(
                name,
                "error",
                f"Set {provider.api_key_env} in the environment, then restart this interface.",
            )
        elif key and (not key.isascii() or any(character.isspace() for character in key)):
            add(name, "error", f"{provider.api_key_env} contains invalid credential characters.")
        else:
            add(name, "ok", f"{provider.model}: endpoint and credential reference configured.")
    add(
        "provider-access",
        "warning",
        "Model availability, credentials, prices and service access are not tested; no API request was made.",
    )

    if config.laya.enabled:
        from .laya import LayaClient

        try:
            LayaClient(config.laya)
            key = os.environ.get(config.laya.api_key_env, "")
            if key and (not key.isascii() or any(c.isspace() for c in key)):
                raise ValueError("Invalid Laya credential characters")
        except ValueError as exc:
            add("laya", "warning", "Optional typed advice is unavailable: " + str(exc))
        else:
            add(
                "laya",
                "warning",
                "Laya typed endpoint configured; access and model availability are untested. "
                "Failures fall back to the independent reasoning agents.",
            )
    from .paper_orchestra import preflight_writer

    writer = preflight_writer(config)
    add(
        "paper-orchestra",
        "ok" if writer["ready"] else "warning",
        "Pinned writer prerequisites configured; live writing remains untested."
        if writer["ready"]
        else "Manuscript stages are blocked until writer setup is complete: "
        + "; ".join(writer["errors"]),
    )
    if writer["unpriced_native_models"]:
        add(
            "writer-pricing",
            "warning",
            "Native writer calls without configured prices use conservative estimated charges: "
            + ", ".join(writer["unpriced_native_models"]),
        )

    project = config.project
    source = Path(project.source_dir).expanduser().resolve()
    included: set[str] = set()
    if not project.source_dir.strip() or not source.is_dir():
        add(
            "source",
            "error",
            "Choose an existing project source directory on the machine running AutoResearch.",
        )
    else:
        try:
            for index, path in enumerate(source.rglob("*")):
                if index > 50000:
                    raise ValueError(
                        "Source directory is too large to inspect; select a smaller project directory."
                    )
                relative = path.relative_to(source)
                if source_is_excluded(relative):
                    continue
                if path.is_symlink() or any(
                    parent.is_symlink() for parent in path.parents if parent != source
                ):
                    continue
                if not path.is_file() or not any(
                    fnmatch.fnmatch(str(relative), pattern) for pattern in project.include
                ):
                    continue
                size = path.stat().st_size
                if size > 5_000_000:
                    raise ValueError(
                        "An included source file exceeds the 5 MB snapshot limit; narrow project.include."
                    )
                included.add(str(relative))
            if not included:
                add(
                    "source",
                    "error",
                    "No project files match project.include; adjust the source directory or include patterns.",
                )
            else:
                add(
                    "source",
                    "ok",
                    f"{len(included)} source files match the snapshot include patterns.",
                )
        except (OSError, ValueError) as exc:
            add("source", "error", str(exc))

    for name, argv in (("baseline", project.baseline_argv), ("evaluator", project.evaluator_argv)):
        if not argv:
            add(name, "error", f"Set project.{name}_argv to a command argument list.")
        elif argv[0] not in config.execution.allowed_executables or any(
            "\x00" in arg for arg in argv
        ):
            add(
                name,
                "error",
                f"The {name} command must use an allowed executable and valid arguments.",
            )
        elif config.execution.backend == "local" and not shutil.which(argv[0]):
            add(name, "error", f"Executable {argv[0]} is not available on this machine.")
        elif (
            argv[0] in {"python", "python3"}
            and len(argv) > 1
            and argv[1].endswith(".py")
            and argv[1] not in included
        ):
            add(
                name,
                "error",
                f"Script {argv[1]} is missing from the source snapshot; check its relative path and include patterns.",
            )
        else:
            add(name, "ok", f"{name.capitalize()} command configured.")
    protected = {
        name
        for name in included
        if any(fnmatch.fnmatch(name, pattern) for pattern in project.protected_paths)
    }
    if not any(arg in protected for arg in project.evaluator_argv[1:]):
        add(
            "protected-evaluator",
            "error",
            "The evaluator command must reference a relative script included in the source snapshot and matched by project.protected_paths.",
        )
    else:
        add(
            "protected-evaluator",
            "ok",
            "Independent evaluator is included and protected from agent edits.",
        )
    missing = set(project.metrics) - set(project.sota)
    if missing:
        add(
            "metrics",
            "error",
            f"Enter original full-benchmark SOTA values for: {', '.join(sorted(missing))}.",
        )
    else:
        add(
            "metrics",
            "ok",
            f"Primary metric: {project.primary_metric}; {len(project.metrics)} comparison metrics.",
        )
    if not project.specification.strip():
        add(
            "protocol",
            "warning",
            "Add a project specification describing data, subset/full splits, outputs and evaluation to guide the agents.",
        )
    if not config.search_enabled:
        add(
            "literature",
            "error",
            "Enable literature search: live citation verification requires independent external retrieval.",
        )
    elif config.search_endpoint != "https://api.crossref.org/works":
        add(
            "literature",
            "error",
            "Built-in literature retrieval requires https://api.crossref.org/works as its Crossref endpoint.",
        )
    if not config.literature.providers or set(config.literature.providers) - {
        "crossref",
        "semantic_scholar",
        "arxiv",
    }:
        add(
            "literature-providers",
            "error",
            "Choose at least one supported literature provider: crossref, semantic_scholar, arxiv.",
        )
    if config.literature.publication_cutoff:
        try:
            date.fromisoformat(config.literature.publication_cutoff)
        except ValueError:
            add(
                "literature-cutoff", "error", "Publication cutoff must be an ISO date (YYYY-MM-DD)."
            )

    try:
        executor = Executor(config.execution)
        if config.execution.readonly_mounts:
            if probe_runtime:
                executor.validate_datasets()
                add(
                    "datasets",
                    "ok",
                    "Dataset mount paths passed local validation; execution checks them again against its workspace.",
                )
            else:
                add("datasets", "warning", "Use Check setup to inspect dataset mount directories.")
    except ExecutionError as exc:
        add("execution", "error", str(exc))
    backend = config.execution.backend
    if backend == "local":
        if not config.execution.allow_local:
            add(
                "execution",
                "error",
                "Local execution requires explicit execution.allow_local=true.",
            )
        elif not shutil.which("python3"):
            add("execution", "error", "python3 is required for the protected evaluator runner.")
        else:
            add(
                "execution",
                "warning",
                "Local execution runs generated code with your user permissions; Docker provides isolation.",
            )
    elif backend == "slurm":
        missing_tools = [
            name for name in ("sbatch", "squeue", "sacct", "scancel") if not shutil.which(name)
        ]
        if missing_tools:
            add(
                "execution",
                "error",
                f"Slurm tools are missing: {', '.join(missing_tools)}. Start this interface on the cluster login node.",
            )
        else:
            add(
                "execution",
                "warning",
                "Slurm tools found. Compute-node Python, shared storage, allocation and dependencies are not tested.",
            )
    else:
        docker = shutil.which("docker")
        if not docker:
            add(
                "execution",
                "error",
                "Docker is not installed or not on PATH. Install/start Docker, or explicitly opt into local execution.",
            )
        elif not probe_runtime:
            add(
                "execution",
                "warning",
                "Docker CLI found. Use Check setup to verify the daemon and image.",
            )
        else:
            for name, argv, failure in (
                (
                    "docker-daemon",
                    [docker, "info", "--format", "{{.ServerVersion}}"],
                    "Docker daemon is unavailable. Start Docker and check setup again.",
                ),
                (
                    "docker-image",
                    [
                        docker,
                        "image",
                        "inspect",
                        config.execution.docker_image,
                        "--format",
                        "{{.Id}}",
                    ],
                    f"Docker image {config.execution.docker_image} is unavailable locally. Pull/build it before starting.",
                ),
            ):
                try:
                    result = subprocess.run(argv, capture_output=True, timeout=3, check=False)
                    available = result.returncode == 0 and bool(result.stdout.strip())
                    add(
                        name,
                        "ok" if available else "error",
                        "Available." if available else failure,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    add(name, "error", failure)
            add(
                "dependencies",
                "warning",
                "Container dependencies and benchmark execution have not been tested.",
            )
    for role, command in config.role_commands.items():
        if not command or not shutil.which(command[0]):
            add(f"adapter:{role}", "error", "Configured role adapter executable is missing.")
        else:
            add(
                f"adapter:{role}",
                "warning",
                "Adapter executable found; its credentials, behavior and cost ceiling enforcement are operator responsibilities.",
            )
    return {"ready": not any(check["status"] == "error" for check in checks), "checks": checks}


def validate_live_config(config: ResearchConfig) -> None:
    result = preflight(config)
    if not result["ready"]:
        raise ValueError(
            "Setup incomplete: "
            + " ".join(check["message"] for check in result["checks"] if check["status"] == "error")
        )
