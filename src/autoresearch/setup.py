"""Local prerequisite checks shared by the terminal and browser setup forms.

Checks do not call models, submit jobs, pull images, or run project commands.
A ready result is not a claim that a benchmark or remote model has been validated.
"""

from __future__ import annotations

import fnmatch
import os
import re
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


class SetupStep(TypedDict):
    owner: Literal["metis", "you"]
    title: str
    message: str
    section: str
    checks: list[str]


class Readiness(TypedDict):
    ready: bool
    checks: list[Check]
    guidance: list[SetupStep]


def guide_checks(checks: list[Check]) -> list[SetupStep]:
    """Present root prerequisites in the order they can be resolved.

    The complete checks remain available and continue to gate run creation. This
    projection is intentionally deterministic; source inspection and AI proposals
    are separate operations with their own trust and cost boundaries.
    """
    errors = {check["name"] for check in checks if check["status"] == "error"}
    warnings = {check["name"] for check in checks if check["status"] == "warning"}
    steps: list[SetupStep] = []

    def step(
        owner: Literal["metis", "you"],
        title: str,
        message: str,
        section: str,
        names: set[str],
    ) -> None:
        steps.append(
            {
                "owner": owner,
                "title": title,
                "message": message,
                "section": section,
                "checks": sorted(names),
            }
        )

    if "source" in errors:
        source_error = next(check["message"] for check in checks if check["name"] == "source")
        if source_error.startswith("Choose an existing project source directory"):
            step(
                "you",
                "Choose a project folder",
                "Point Metis to the source directory on this machine. It can then inspect files and suggest the next setup choices.",
                "project",
                {"source"},
            )
        else:
            include_problem = source_error.startswith(
                ("No project files match", "An included source file exceeds")
            )
            step(
                "you",
                "Review the source snapshot",
                source_error
                + (
                    " Adjust project.include in Advanced configuration, or choose a different folder in Project."
                    if include_problem
                    else " Choose a smaller source folder in Project."
                ),
                "advanced" if include_problem else "project",
                {"source"},
            )
    else:
        project_errors = errors & {"baseline", "evaluator", "protected-evaluator"}
        project_work = project_errors | ({"protocol"} if "protocol" in warnings else set())
        if project_work:
            step(
                "metis",
                "Inspect the project",
                "Metis can inspect source files, suggest commands and protected evaluation files, and draft a protocol. Review the evidence, fixed splits and restrictions before using them.",
                "project",
                project_work,
            )
        if "metrics" in errors:
            step(
                "you",
                "Provide the benchmark reference",
                "Enter the published full-benchmark value and its source. Metis cannot replace it with a subset result or an invented value.",
                "project",
                {"metrics"},
            )

    provider_errors = {name for name in errors if name.startswith("provider:")}
    if provider_errors:
        step(
            "you",
            "Connect a model provider",
            "Use an environment variable name in Model, then set its credential in the Metis server environment. Metis checks the reference without displaying its value.",
            "model",
            provider_errors,
        )

    if "docker-daemon" in errors:
        step(
            "you",
            "Start Docker",
            "Start the Docker daemon on this machine, then check setup again.",
            "execution",
            {"docker-daemon"},
        )
    elif "docker-image" in errors:
        step(
            "you",
            "Prepare a Docker image",
            "Choose or build an image with the project's dependencies, then check setup again.",
            "execution",
            {"docker-image"},
        )
    if "execution" in errors:
        step(
            "you",
            "Choose an available execution environment",
            "Configure Docker, a supported Slurm host, or explicitly allow local execution for a trusted workspace.",
            "execution",
            {"execution"},
        )

    covered = {name for item in steps for name in item["checks"]}
    for check in checks:
        if check["status"] != "error" or check["name"] in covered:
            continue
        # Source-dependent checks are useful diagnostics, but not separate
        # requests while the source directory itself is absent.
        if "source" in errors and check["name"] in {
            "baseline",
            "evaluator",
            "protected-evaluator",
            "metrics",
        }:
            continue
        if "docker-daemon" in errors and check["name"] == "docker-image":
            continue
        step(
            "you",
            check["name"].replace("-", " ").capitalize(),
            check["message"],
            "advanced",
            {check["name"]},
        )
    return steps


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
        return {
            "ready": not any(check["status"] == "error" for check in checks),
            "checks": checks,
            "guidance": guide_checks(checks),
        }

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
            "Choose an existing project source directory on the machine running Metis.",
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
    # A successful submission command is not a completed, tracked experiment.
    for name, argv in (("baseline", project.baseline_argv), ("evaluator", project.evaluator_argv)):
        nested = bool(argv and Path(argv[0]).name in {"sbatch", "salloc"})
        for arg in argv[1:]:
            if arg not in included or not arg.endswith((".sh", ".sbatch")):
                continue
            from .onboarding import read_project_excerpt

            script = read_project_excerpt(source, arg, 100000) or ""
            nested = (
                nested
                or arg.endswith(".sbatch")
                or bool(re.search(r"(?:^|[\s;])(?:sbatch|salloc)(?:\s|$)", script))
            )
        if nested:
            add(
                "execution-launcher",
                "error",
                f"The {name} command submits a separate scheduler job. Metis cannot treat submission as experiment completion. Integrate its launcher with job tracking and GPU allocation before starting research.",
            )
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
    return {
        "ready": not any(check["status"] == "error" for check in checks),
        "checks": checks,
        "guidance": guide_checks(checks),
    }


def validate_live_config(config: ResearchConfig) -> None:
    result = preflight(config)
    if not result["ready"]:
        raise ValueError(
            "Setup incomplete: "
            + " ".join(check["message"] for check in result["checks"] if check["status"] == "error")
        )
