"""Local prerequisite checks shared by the terminal and browser setup forms.

Checks do not call models, submit jobs, pull images, or run project commands.
A ready result is not a claim that a benchmark or remote model has been validated.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from .config import ResearchConfig
from .credentials import CredentialAccessError, resolve
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
    source_files: list[str]
    source_file_count: int


class SetupRecovery(TypedDict):
    config: dict[str, object]
    readiness: Readiness
    actions: list[str]


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
                "Choose the folder containing the project on this machine. Metis can then inspect its files and suggest the next setup choices.",
                "project",
                {"source"},
            )
        else:
            can_select = source_error.startswith(
                ("No project files were selected", "A selected project file is larger")
            )
            step(
                "metis" if can_select else "you",
                "Select project files" if can_select else "Choose a project folder",
                "Metis can inspect this folder and select the project files it can safely use."
                if can_select
                else source_error,
                "project",
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
            "Add an API key in Model access or set the named variable in the Metis server environment. Metis checks for a key without displaying it.",
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
            "metis",
            "Prepare a Docker image",
            "Metis can fetch the configured image. Its project dependencies still need verification before research.",
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


def recover_setup(config: ResearchConfig) -> SetupRecovery:
    """Perform bounded mechanical setup recovery for an explicit browser check.

    The returned configuration is a proposal for the unsaved form. This operation
    never runs project commands or changes a stored run.
    """
    proposed = config.model_copy(deep=True)
    actions: list[str] = []
    source_reason = ""
    readiness = preflight(proposed, probe_runtime=True)
    errors = {check["name"] for check in readiness["checks"] if check["status"] == "error"}
    hidden_script = _required_script_outside_selection(proposed)

    if ("source" in errors or hidden_script) and proposed.project.source_dir.strip():
        from .onboarding import inspect_project

        try:
            inspection = inspect_project(proposed.project.source_dir)
            # An incomplete inventory is not a safe basis for an exact snapshot.
            files = inspection["files"]
            if inspection["inventory_truncated"]:
                source_reason = "This folder has too many files for Metis to inspect safely. Choose a smaller folder containing the project code."
            elif len(files) > 200:
                source_reason = f"Metis found {len(files)} files, more than the 200 it can select automatically. Choose a smaller folder containing the project code."
            elif files:
                root = Path(proposed.project.source_dir).expanduser().resolve()
                eligible = [name for name in files if _snapshot_candidate(root, name)]
                context_sizes = [
                    (root / name).stat().st_size
                    for name in eligible
                    if Path(name).suffix in {".py", ".toml", ".md", ".json", ".sh"}
                    and not Path(name).name.startswith(".autoresearch")
                ]
                if (
                    any(size > 1_000_000 for size in context_sizes)
                    or sum(context_sizes) > 2_000_000
                ):
                    source_reason = "The project text is too large for Metis to inspect safely. Choose a smaller folder containing the project code."
                elif eligible and eligible != proposed.project.include:
                    proposed.project.include = [_literal_glob(name) for name in eligible]
                    candidate = preflight(proposed, probe_runtime=False)
                    if any(
                        check["name"] == "source" and check["status"] == "ok"
                        for check in candidate["checks"]
                    ):
                        actions.append(f"Selected {len(eligible)} project files.")
                    else:
                        proposed.project.include = list(config.project.include)
                        source_reason = "Metis could not use the files in this folder. Choose a smaller folder containing the project code."
                else:
                    source_reason = "Metis found no project files it can use in this folder. Choose a folder containing the project code."
            else:
                source_reason = "Metis found no project files in this folder. Choose a folder containing the project code."
        except (OSError, ValueError):
            source_reason = "Metis could not inspect this folder. Choose an accessible folder containing the project code."

    if (
        proposed.execution.backend == "docker"
        and "docker-image" in errors
        and "docker-daemon" not in errors
    ):
        docker = shutil.which("docker")
        if docker:
            try:
                built = _build_python_image(docker, proposed)
                if built:
                    proposed.execution.docker_image = built
                    if not any(
                        fnmatch.fnmatch("requirements.txt", pattern)
                        for pattern in proposed.project.include
                    ):
                        proposed.project.include.append("requirements.txt")
                    actions.append(
                        "Built a Docker image with the pinned Python requirements in the project folder."
                    )
                elif _unhandled_dependencies(proposed):
                    actions.append(
                        "Project dependencies need review before Metis can prepare an image. Use a pinned requirements.txt or select an existing project image."
                    )
                else:
                    result = subprocess.run(
                        [docker, "pull", proposed.execution.docker_image],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=180,
                        check=False,
                    )
                    if result.returncode == 0:
                        actions.append(f"Fetched Docker image {proposed.execution.docker_image}.")
                    else:
                        actions.append(
                            "The Docker image could not be fetched. Check the image name and registry access."
                        )
            except (OSError, subprocess.TimeoutExpired):
                actions.append(
                    "Docker image preparation did not complete. Check Docker and registry access."
                )

    final_readiness = preflight(proposed, probe_runtime=True)
    if source_reason and ("source" in errors or hidden_script):
        for step in final_readiness["guidance"]:
            if "source" in step["checks"] or (
                hidden_script
                and set(step["checks"]) & {"baseline", "evaluator", "protected-evaluator"}
            ):
                step["owner"] = "you"
                step["title"] = "Choose a project folder"
                step["message"] = source_reason
                step["section"] = "project"
                break
    return {
        "config": proposed.model_dump(mode="json"),
        "readiness": final_readiness,
        "actions": actions,
    }


def _snapshot_candidate(root: Path, name: str) -> bool:
    path = root / name
    if source_is_excluded(name) or any(
        parent.is_symlink() for parent in path.parents if parent != root
    ):
        return False
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 5_000_000:
                return False
            os.read(fd, 1)
            return True
        finally:
            os.close(fd)
    except OSError:
        return False


def _required_script_outside_selection(config: ResearchConfig) -> bool:
    """Detect an existing command script hidden by stale file selection."""
    if not config.project.source_dir.strip():
        return False
    root = Path(config.project.source_dir).expanduser().resolve()
    if not root.is_dir():
        return False
    for argv in (config.project.baseline_argv, config.project.evaluator_argv):
        if len(argv) < 2 or Path(argv[0]).name not in {"python", "python3", "sh", "bash"}:
            continue
        name = argv[1]
        relative = Path(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix
            not in {
                ".py",
                ".sh",
                ".sbatch",
            }
        ):
            continue
        if any(fnmatch.fnmatch(name, pattern) for pattern in config.project.include):
            continue
        if _snapshot_candidate(root, name):
            return True
    return False


def _literal_glob(name: str) -> str:
    """Encode an inventoried filename for the existing fnmatch include contract."""
    return "".join(
        {"[": "[[]", "]": "[]]", "?": "[?]", "*": "[*]"}.get(char, char) for char in name
    )


def _build_python_image(docker: str, config: ResearchConfig) -> str | None:
    """Build with a vetted manifest; never send the source tree to Docker."""
    if config.execution.docker_image != "python:3.11-slim" or not config.project.source_dir:
        return None
    source = Path(config.project.source_dir).expanduser().resolve()
    manifest = source / "requirements.txt"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 64_000:
        return None
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except UnicodeError:
        return None
    requirements = [
        line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]
    pinned = re.compile(
        r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9_.+!-]*"
    )
    if (
        not requirements
        or len(requirements) > 100
        or any(not pinned.fullmatch(line) for line in requirements)
    ):
        return None
    content = "\n".join(requirements) + "\n"
    tag = "metis-project:" + hashlib.sha256(content.encode()).hexdigest()[:16]
    with tempfile.TemporaryDirectory(prefix="metis-image-") as directory:
        context = Path(directory)
        (context / "requirements.txt").write_text(content)
        (context / "Dockerfile").write_text(
            "FROM python:3.11-slim\n"
            "COPY requirements.txt /tmp/requirements.txt\n"
            "RUN python -m pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt\n"
        )
        result = subprocess.run(
            [docker, "build", "--tag", tag, str(context)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            raise OSError("Docker build failed")
    inspected = subprocess.run(
        [docker, "image", "inspect", tag, "--format", "{{.Id}}"],
        capture_output=True,
        timeout=3,
        check=False,
    )
    image_id = inspected.stdout.decode("ascii", errors="ignore").strip()
    if inspected.returncode != 0 or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise OSError("Built image could not be identified")
    return image_id


def _unhandled_dependencies(config: ResearchConfig) -> bool:
    if config.execution.docker_image != "python:3.11-slim" or not config.project.source_dir:
        return False
    root = Path(config.project.source_dir).expanduser().resolve()
    names = {path.name.lower() for path in root.iterdir()}
    known = {
        "pyproject.toml",
        "environment.yml",
        "environment.yaml",
        "pipfile",
        "dockerfile",
        "package.json",
        "setup.py",
        "setup.cfg",
        "uv.lock",
        "poetry.lock",
        "pdm.lock",
        "cargo.toml",
        "cargo.lock",
        "go.mod",
        "go.sum",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "gemfile",
        "gemfile.lock",
        "composer.json",
        "composer.lock",
    }
    return bool(names & known) or any(
        name.startswith("requirements")
        and name.endswith(".txt")
        or name.endswith(".lock")
        or name.startswith("dockerfile.")
        for name in names
    )


def preflight(config: ResearchConfig, *, probe_runtime: bool = False) -> Readiness:
    checks: list[Check] = []

    def add(name: str, status: Literal["ok", "error", "warning"], message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})

    try:
        from .model_inventory import prepare_models

        config = prepare_models(config)
        from .model_inventory import guard_writer_models

        try:
            guard_writer_models(config)
        except ValueError as exc:
            add("writer-model-permissions", "warning", str(exc))
    except ValueError as exc:
        add("provider:inventory", "error", str(exc))

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
            "source_files": [],
            "source_file_count": 0,
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
        try:
            key, credential_source = resolve(provider.api_key_env)
        except CredentialAccessError as exc:
            add(name, "error", str(exc))
            continue
        if not provider.model.strip():
            add(name, "error", "Set a model identifier.")
        elif not key and not local:
            add(
                name,
                "error",
                f"Add a key for {provider.api_key_env} in Model access, or set it in the server environment.",
            )
        elif key and (not key.isascii() or any(character.isspace() for character in key)):
            add(name, "error", f"{provider.api_key_env} contains invalid credential characters.")
        else:
            add(
                name,
                "ok",
                f"{provider.model}: endpoint and {credential_source} credential configured.",
            )
    add(
        "provider-access",
        "warning",
        "Model availability, credentials, prices and service access are not tested; no API request was made.",
    )

    if config.laya.enabled:
        from .laya import LayaClient

        try:
            LayaClient(config.laya)
            key, _ = resolve(config.laya.api_key_env)
            if key and (not key.isascii() or any(c.isspace() for c in key)):
                raise ValueError("Invalid Laya credential characters")
        except (ValueError, CredentialAccessError) as exc:
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

    if config.entry_mode == "agent":
        if config.project.source_dir and not Path(config.project.source_dir).expanduser().is_dir():
            add(
                "source",
                "error",
                "Choose an existing project folder or leave it blank for a new workspace.",
            )
        else:
            add(
                "research-input",
                "ok",
                "The initial agent will inspect papers and project resources. Baseline commands, metrics and measurement are established during research.",
            )
        if not config.search_enabled:
            add(
                "literature",
                "error",
                "Enable literature search for source-grounded research intake.",
            )
        add(
            "execution",
            "warning",
            "Compute and data access are checked when experiments need them; they do not prevent research intake.",
        )
        return {
            "ready": not any(check["status"] == "error" for check in checks),
            "checks": checks,
            "guidance": guide_checks(checks),
            "source_files": [],
            "source_file_count": 0,
        }

    project = config.project
    source = Path(project.source_dir).expanduser().resolve()
    included: set[str] = set()
    eligible_count = 0
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
                if not path.is_file():
                    continue
                eligible_count += 1
                if not any(fnmatch.fnmatch(str(relative), pattern) for pattern in project.include):
                    continue
                size = path.stat().st_size
                if size > 5_000_000:
                    raise ValueError(
                        "A selected project file is larger than Metis's 5 MB file limit."
                    )
                included.add(str(relative))
            if not included:
                add(
                    "source",
                    "error",
                    "No usable project files were found in this folder. Choose a folder containing project code."
                    if not eligible_count
                    else "No project files were selected from this folder.",
                )
            else:
                add(
                    "source",
                    "ok",
                    f"{len(included)} project files selected.",
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
                f"Script {argv[1]} is missing from the selected project files. Check the script path in Project.",
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
            "The independent evaluation script must be one of the selected project files and listed as protected in Project.",
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
        "source_files": sorted(included)[:200]
        if any(check["name"] == "source" and check["status"] == "ok" for check in checks)
        else [],
        "source_file_count": len(included)
        if any(check["name"] == "source" and check["status"] == "ok" for check in checks)
        else 0,
    }


def validate_live_config(config: ResearchConfig) -> None:
    result = preflight(config)
    if not result["ready"]:
        raise ValueError(
            "Setup incomplete: "
            + " ".join(check["message"] for check in result["checks"] if check["status"] == "error")
        )
