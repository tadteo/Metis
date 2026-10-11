"""Local prerequisite checks shared by the terminal and browser setup forms.

Checks do not call models, submit jobs, pull images, or run project commands.
A ready result is not a claim that a benchmark or remote model has been validated.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict
from urllib.parse import urlsplit

from . import isolation
from .config import ResearchConfig
from .credentials import CredentialAccessError, resolve
from .execution import ExecutionError, Executor
from .providers import ProviderError, create_provider
from .source_policy import source_is_excluded

if TYPE_CHECKING:
    from .model_inventory import ModelInventory


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
    # Automatic per-role model plan (deterministic preview; no model call).
    model_plan: NotRequired[dict[str, Any]]


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

    for runtime, start in (
        ("docker", "Start the Docker daemon on this machine, then check setup again."),
        ("podman", "Start Podman (on macOS: podman machine start), then check setup again."),
    ):
        title = runtime.capitalize()
        if f"{runtime}-daemon" in errors:
            step("you", f"Start {title}", start, "execution", {f"{runtime}-daemon"})
        elif f"{runtime}-image" in errors:
            step(
                "metis",
                f"Prepare a {title} image",
                "Metis can fetch the configured image. Its project dependencies still need verification before research.",
                "execution",
                {f"{runtime}-image"},
            )
    if "podman-limits" in errors and "podman-daemon" not in errors:
        step(
            "you",
            "Enable Podman resource limits",
            "Rootless Podman needs cgroups v2 with cpu, memory and pids delegated to your user. Ask the administrator, or choose Docker or Apptainer.",
            "execution",
            {"podman-limits"},
        )
    if errors & {"apptainer", "apptainer-image"}:
        step(
            "you",
            "Prepare Apptainer",
            "Install or load Apptainer on this host and set an existing .sif image, for example from apptainer pull image.sif docker://python:3.11-slim.",
            "execution",
            errors & {"apptainer", "apptainer-image"},
        )
    if "environment" in errors:
        step(
            "you",
            "Choose a Python environment",
            "Enter the folder of a venv, conda or uv environment on the execution host, or leave it empty to use python3 from PATH.",
            "execution",
            {"environment"},
        )
    if "execution" in errors:
        step(
            "you",
            "Choose an available execution environment",
            "Configure Docker, Podman, Apptainer, the native sandbox, a supported Slurm host, or explicitly allow local execution for a trusted workspace.",
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
        if check["name"] in {"docker-image", "podman-image", "podman-limits"} and (
            check["name"].split("-")[0] + "-daemon" in errors
        ):
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

    runtime = proposed.execution.backend
    if (
        runtime in {"docker", "podman"}
        and f"{runtime}-image" in errors
        and f"{runtime}-daemon" not in errors
    ):
        docker = shutil.which(runtime)
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
                        f"Built a {runtime.capitalize()} image with the pinned Python requirements in the project folder."
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
                        actions.append(
                            f"Fetched {runtime.capitalize()} image {proposed.execution.docker_image}."
                        )
                    else:
                        actions.append(
                            f"The {runtime.capitalize()} image could not be fetched. Check the image name and registry access."
                        )
            except (OSError, subprocess.TimeoutExpired):
                actions.append(
                    f"{runtime.capitalize()} image preparation did not complete. Check {runtime.capitalize()} and registry access."
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
    # Docker prints sha256:<hex>; Podman prints the bare hex identifier.
    image_id = inspected.stdout.decode("ascii", errors="ignore").strip().removeprefix("sha256:")
    if inspected.returncode != 0 or not re.fullmatch(r"[0-9a-f]{64}", image_id):
        raise OSError("Built image could not be identified")
    return "sha256:" + image_id


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


def inventory_checks(inventory: ModelInventory | None) -> list[Check]:
    """Per-model key presence and published limits. No provider request is made."""
    from .model_inventory import access

    checks: list[Check] = []
    for entry in inventory.models if inventory else []:
        if not entry.enabled:
            continue
        state = access(entry)
        env = entry.provider.api_key_env
        if state["status"] == "configured":
            local = state["source"] == "missing"
            status: Literal["ok", "error", "warning"] = "ok"
            message = (
                f"{entry.label}: loopback server; no key needed."
                if local
                else f"{entry.label}: key {env} present ({state['source']})."
            )
        elif state["status"] == "key_needed":
            status = "warning"
            message = (
                f"{entry.label}: key {env} missing. Metis will not select this model until "
                "you add the key in Settings → Model access or the server environment."
            )
        else:
            status = "warning"
            message = (
                f"{entry.label}: {state['status'].replace('_', ' ')}; Metis will not select it."
            )
        preset = entry.preset
        if preset is not None:
            from .provider_presets import limits_text

            if preset.key_required:
                message += " " + limits_text(preset.model, preset.tier)
            if preset.data_use is not None:
                message += " Data use: " + preset.data_use.text
            message += f" (Catalog figures checked {preset.catalog_version.isoformat()}.)"
        checks.append({"name": f"model:{entry.id}", "status": status, "message": message})
    return checks


Add = Callable[[str, Literal["ok", "error", "warning"], str], None]


def _python_runs_module_or_code(argv: list[str]) -> bool:
    """Whether a Python command uses -m or -c, which put the working directory on sys.path."""
    if not argv or not Path(argv[0]).name.startswith("python"):
        return False
    arguments = iter(argv[1:])
    for argument in arguments:
        if not argument.startswith("-") or argument == "-":
            return False
        if argument.startswith(("-m", "-c")):
            return True
        if argument in {"-X", "-W", "--check-hash-based-pycs"}:
            next(arguments, None)  # option value
    return False


def _native_available(name: str, environment_dir: str) -> bool:
    try:
        isolation.resolve_native(name, environment_dir)
    except ExecutionError:
        return False
    return True


def _check_environment(config: ResearchConfig, add: Add) -> None:
    """A configured Python environment must provide the allowed interpreters."""
    directory = Path(config.execution.environment_dir)
    try:
        executables = isolation.environment_bin(config.execution.environment_dir)
    except ExecutionError as exc:
        add("environment", "error", str(exc))
        return
    if executables is None or not directory.is_dir():
        add("environment", "error", f"Python environment {directory} does not exist on this host.")
    elif not shutil.which("python3", path=str(executables)):
        add(
            "environment",
            "error",
            f"Python environment {directory} has no {executables.name}/python3. Choose the environment prefix, such as a .venv or conda environment folder.",
        )
    elif config.execution.backend == "slurm":
        add(
            "environment",
            "warning",
            "Python environment found on this host. Compute nodes must see the same path on shared storage.",
        )
    else:
        add("environment", "ok", f"Python environment {directory} found.")


def _probe(argv: list[str], timeout: float = 5) -> bool:
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _check_sandbox(config: ResearchConfig, add: Add, probe_runtime: bool) -> None:
    try:
        kind = isolation.sandbox_kind()
    except ExecutionError as exc:
        add("execution", "error", str(exc))
        return
    tool = "sandbox-exec" if kind == "seatbelt" else "bwrap"
    found = shutil.which(tool)
    if not found:
        add(
            "execution",
            "error",
            "sandbox-exec is missing from this macOS installation. Choose Docker or Podman instead."
            if kind == "seatbelt"
            else "bubblewrap (bwrap) is not installed. Install it, or choose Apptainer, Podman or Docker.",
        )
        return
    true = shutil.which("true") or "/bin/true"
    if probe_runtime and kind == "bubblewrap":
        if not _probe([found, "--ro-bind", "/", "/", "--unshare-all", "--die-with-parent", true]):
            add(
                "execution",
                "error",
                "bubblewrap cannot create a sandbox here; unprivileged user namespaces may be disabled. Ask the administrator, or choose Apptainer.",
            )
            return
    if probe_runtime and kind == "seatbelt":
        if not _probe([found, "-p", "(version 1)(allow default)", true]):
            add("execution", "error", "sandbox-exec could not start a sandboxed process.")
            return
    add(
        "execution",
        "warning",
        "Sandbox available: no network, writes only to the experiment directory, home and Metis state hidden. "
        "It runs natively with your Python environment; it is an OS sandbox, not a container or virtual machine. "
        "Dependencies and benchmark execution have not been tested.",
    )


def _apptainer_version(tool: str) -> tuple[Literal["ok", "error", "warning"], str] | None:
    """Metis needs --no-eval: Apptainer >= 1.1 or SingularityCE >= 3.10."""
    try:
        result = subprocess.run([tool, "--version"], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "error", f"{Path(tool).name} did not run. Check its installation."
    text = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"(apptainer|singularity-ce|singularity) version (\d+)\.(\d+)", text)
    if result.returncode or not match:
        return (
            "warning",
            f"Could not read the {Path(tool).name} version; Metis needs Apptainer 1.1+ or SingularityCE 3.10+.",
        )
    name, major, minor = match.group(1), int(match.group(2)), int(match.group(3))
    minimum = (1, 1) if name == "apptainer" else (3, 10)
    if name == "singularity" or (major, minor) < minimum:
        return (
            "error",
            f"{name} {major}.{minor} is too old: Metis needs Apptainer 1.1+ or SingularityCE 3.10+ (for --no-eval).",
        )
    return None


def _check_apptainer(
    config: ResearchConfig, add: Add, probe_runtime: bool, *, scheduled: bool
) -> None:
    image = config.execution.apptainer_image
    tool = shutil.which("apptainer") or shutil.which("singularity")
    if not tool:
        add(
            "apptainer",
            "error",
            "Apptainer (or SingularityCE) is not installed on this host. On a cluster, load or install it on the login node.",
        )
    elif probe_runtime:
        add_check = _apptainer_version(tool)
        if add_check:
            add("apptainer", *add_check)
    if not image:
        add(
            "apptainer-image",
            "error",
            "Set the Apptainer image: an absolute .sif path, or a docker:// reference to convert.",
        )
    elif "://" in image:
        add(
            "apptainer-image",
            "warning",
            "Apptainer resolves registry images at run time; compute nodes may lack network access. "
            "Prefer a local SIF: apptainer pull image.sif " + image,
        )
    elif not Path(image).is_file():
        add("apptainer-image", "error", f"Apptainer image {image} does not exist on this host.")
    else:
        add(
            "apptainer-image",
            "warning" if scheduled else "ok",
            "Apptainer image found. Compute nodes must see the same path on shared storage."
            if scheduled
            else "Apptainer image found. Its dependencies have not been tested.",
        )
        if tool and probe_runtime:
            problem = _apptainer_isolation(tool, image)
            add("apptainer-isolation", "error" if problem else "ok", problem or "Contained.")


# Printed inside the image: the PID-namespace facts the trusted runner relies on.
_NAMESPACE_PROBE = (
    "import json, os; print(json.dumps({'pid': os.getpid(), 'parent': os.getppid()}))"
)


def _apptainer_isolation(tool: str, image: str) -> str:
    """Run the image as experiments do; protected evaluation needs a private PID namespace."""
    argv = [tool, "exec", "--containall", "--no-eval", "--net", "--network", "none"]
    try:
        result = subprocess.run(
            [*argv, image, "python3", "-c", _NAMESPACE_PROBE],
            capture_output=True,
            timeout=120,
            check=False,
        )
        facts = json.loads(result.stdout.decode("utf-8", errors="replace").strip().splitlines()[-1])
        pid, parent = int(facts["pid"]), int(facts["parent"])
        nested = pid == 1 or (pid == 2 and parent == 1)
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, TypeError):
        return (
            "The image did not run with --containall and --network none, or lacks python3. "
            "Check that unprivileged network and PID namespaces are allowed."
        )
    if result.returncode or not nested:
        return (
            "Apptainer does not give experiments a private PID namespace here "
            "(allow pid ns = no?), so protected evaluation would be refused."
        )
    return ""


def _check_container(config: ResearchConfig, add: Add, probe_runtime: bool) -> None:
    """Docker and Podman share isolation flags and image references."""
    backend = config.execution.backend
    title = backend.capitalize()
    tool = shutil.which(backend)
    if not tool:
        add(
            "execution",
            "error",
            f"{title} is not installed or not on PATH. Install/start {title}, or choose another backend such as Sandbox.",
        )
        return
    if not probe_runtime:
        add(
            "execution",
            "warning",
            f"{title} CLI found. Use Check setup to verify the {'daemon' if backend == 'docker' else 'service'} and image.",
        )
        return
    image = config.execution.docker_image
    daemon = (
        "Docker daemon is unavailable. Start Docker and check setup again."
        if backend == "docker"
        else "Podman is unavailable. Start it (on macOS: podman machine start) and check setup again."
    )
    for name, argv, failure in (
        (
            f"{backend}-daemon",
            [
                tool,
                "info",
                "--format",
                "{{.ServerVersion}}" if backend == "docker" else "{{.Version.Version}}",
            ],
            daemon,
        ),
        (
            f"{backend}-image",
            [tool, "image", "inspect", image, "--format", "{{.Id}}"],
            f"{title} image {image} is unavailable locally. Pull/build it before starting.",
        ),
    ):
        try:
            result = subprocess.run(argv, capture_output=True, timeout=3, check=False)
            available = result.returncode == 0 and bool(result.stdout.strip())
            add(name, "ok" if available else "error", "Available." if available else failure)
        except (OSError, subprocess.TimeoutExpired):
            add(name, "error", failure)
    if backend == "podman":
        try:
            result = subprocess.run(
                [tool, "info", "--format", "json"], capture_output=True, timeout=10, check=False
            )
            problem = isolation.podman_limits_problem(
                isolation.podman_mode(result.stdout.decode("utf-8", errors="replace"))
            )
        except (OSError, subprocess.TimeoutExpired, ExecutionError) as exc:
            problem = str(exc) or "Podman is unavailable"
        add("podman-limits", "error" if problem else "ok", problem or "Resource limits available.")
    add(
        "dependencies",
        "warning",
        "Container dependencies and benchmark execution have not been tested.",
    )


def preflight(config: ResearchConfig, *, probe_runtime: bool = False) -> Readiness:
    checks: list[Check] = []

    def add(name: str, status: Literal["ok", "error", "warning"], message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})

    configured_inventory = config.model_inventory
    model_plan: dict[str, Any] | None = None
    try:
        from .model_inventory import plan_and_prepare

        # Deterministic: inspects local configuration only and makes no model call.
        config, plan = plan_and_prepare(config)
        if plan is not None:
            from .model_selection import preview

            model_plan = preview(plan)
            add(
                "model-plan",
                "warning" if plan["warnings"] else "ok",
                model_plan["summary"],
            )
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
    environment_keys: list[str] = []
    for role, provider in providers.items():
        name = f"provider:{role}"
        try:
            create_provider(provider)
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
            if key and credential_source == "environment":
                environment_keys.append(provider.api_key_env)
            add(
                name,
                "ok",
                f"{provider.model}: endpoint and {credential_source} credential configured.",
            )
    if environment_keys and config.execution.backend == "sandbox" and sys.platform == "darwin":
        add(
            "sandbox-credentials",
            "warning",
            "On macOS, sandboxed experiments can read the environment of processes running as you. "
            f"Save {', '.join(sorted(set(environment_keys)))} in Model access (the OS vault) and "
            "remove it from the environment that starts Metis.",
        )
    for entry_check in inventory_checks(configured_inventory):
        checks.append(entry_check)
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
        intake: Readiness = {
            "ready": not any(check["status"] == "error" for check in checks),
            "checks": checks,
            "guidance": guide_checks(checks),
            "source_files": [],
            "source_file_count": 0,
        }
        if model_plan is not None:
            intake["model_plan"] = model_plan
        return intake

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
        elif config.execution.backend in {"local", "sandbox"} and not _native_available(
            argv[0], config.execution.environment_dir
        ):
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
    if _python_runs_module_or_code(project.evaluator_argv):
        add(
            "evaluator-path",
            "warning",
            "Run the evaluator as a script (python3 evaluate.py): with -m or -c Python imports "
            "from the experiment directory, where generated code could place modules.",
        )
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
    native = backend in {"local", "sandbox"} or (
        backend == "slurm" and config.execution.slurm_container == "none"
    )
    if config.execution.environment_dir and native:
        _check_environment(config, add)
    if backend == "local":
        if not config.execution.allow_local:
            add(
                "execution",
                "error",
                "Local execution requires explicit execution.allow_local=true.",
            )
        elif not _native_available("python3", config.execution.environment_dir):
            add("execution", "error", "python3 is required for the protected evaluator runner.")
        else:
            add(
                "execution",
                "warning",
                "Local execution runs generated code with your user permissions; Docker provides isolation.",
            )
    elif backend == "sandbox":
        _check_sandbox(config, add, probe_runtime)
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
        if config.execution.slurm_container == "apptainer":
            _check_apptainer(config, add, probe_runtime, scheduled=True)
    elif backend == "apptainer":
        _check_apptainer(config, add, probe_runtime, scheduled=False)
    else:
        _check_container(config, add, probe_runtime)
    for role, command in config.role_commands.items():
        if not command or not shutil.which(command[0]):
            add(f"adapter:{role}", "error", "Configured role adapter executable is missing.")
        else:
            add(
                f"adapter:{role}",
                "warning",
                "Adapter executable found; its credentials, behavior and cost ceiling enforcement are operator responsibilities.",
            )
    readiness: Readiness = {
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
    if model_plan is not None:
        readiness["model_plan"] = model_plan
    return readiness


def validate_live_config(config: ResearchConfig) -> None:
    result = preflight(config)
    if not result["ready"]:
        raise ValueError(
            "Setup incomplete: "
            + " ".join(check["message"] for check in result["checks"] if check["status"] == "error")
        )
