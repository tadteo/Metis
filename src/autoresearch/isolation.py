"""Argv builders for experiment runtimes other than Docker and plain subprocesses.

Every builder returns an argument vector; no shell is involved. Paths enter sandbox
profiles only as ``-D`` parameters referenced by generated names, so a path can never
become profile syntax. The caller (``execution.Executor``) authorizes the workload
argv, prepares the workspace and owns receipts.

These boundaries are defense in depth around generated code, not a virtual machine.
Containers (Docker, Podman, Apptainer) isolate a separate root filesystem. The native
sandbox hides selected host locations from a process that otherwise runs natively.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .runtime_support import ExecutionError

# Mach services a native scientific Python workload needs on macOS: user lookup, power
# assertions and Metal shader compilation for MPS. Keychain, LaunchServices, Apple Events,
# launchd job submission and every other service stay denied.
_MACH_SERVICES = (
    "com.apple.MTLCompilerService",
    "com.apple.PowerManagement.control",
    "com.apple.system.opendirectoryd.libinfo",
)
# Shared-memory names used by PyTorch, multiprocessing.shared_memory and OpenMP.
_SHM_NAMES = r"^/(torch_|psm_|__KMP_REGISTERED_LIB_)"

# Shared host locations that hold other users' or applications' private data, sockets
# or credentials. The sandbox re-allows only the paths an experiment needs.
_MAC_HIDDEN = ("/Users", "/Volumes", "/private/var/folders", "/private/tmp", "/private/var/run")
# Hidden (replaced by empty tmpfs), not used as temporary storage.
_LINUX_HIDDEN = ("/home", "/root", "/run", "/tmp", "/var/tmp", "/mnt", "/media", "/srv")  # noqa: S108


@dataclass
class SandboxPaths:
    """Canonical host paths for one native sandboxed command."""

    workspace: Path
    private_tmp: Path
    hidden: list[Path] = field(default_factory=list)
    readable: list[Path] = field(default_factory=list)
    protected: list[Path] = field(default_factory=list)
    gpu_devices: list[Path] = field(default_factory=list)


def canonical(path: Path) -> Path:
    """Resolve symlinks such as /tmp -> /private/tmp; sandboxes match real paths."""
    return Path(os.path.realpath(path))


def sandbox_kind() -> str:
    """The native sandbox available on this operating system, or a clear error."""
    if sys.platform == "darwin":
        return "seatbelt"
    if sys.platform.startswith("linux"):
        return "bubblewrap"
    raise ExecutionError("The sandbox backend supports macOS (sandbox-exec) and Linux (bubblewrap)")


# Metis state and database directories opened in this process (see Store).
_REGISTERED_ROOTS: set[Path] = set()


def register_private_root(path: Path) -> None:
    """Record a Metis state or database directory that sandboxes must hide."""
    _REGISTERED_ROOTS.add(canonical(path))


def private_roots(workspace: Path) -> list[Path]:
    """Metis state and database roots that contain other runs, prompts and results.

    Every Store registers its state and database directories, including ``--state-dir``
    and ``--db-dir``; the environment overrides and the ``<state>/runs/<run>/`` layout
    cover a workspace whose store was opened elsewhere.
    """
    roots = [canonical(Path.home()), *sorted(_REGISTERED_ROOTS)]
    for name in ("AUTORESEARCH_HOME", "AUTORESEARCH_DB_DIR"):
        if os.environ.get(name):
            roots.append(canonical(Path(os.environ[name]).expanduser()))
    for parent in workspace.parents:
        if parent.name == "runs":
            roots.append(parent.parent)
            break
    # The workspace's own parent holds sibling experiments and snapshots.
    roots.append(workspace.parent)
    return list(dict.fromkeys(roots))


def interpreter_prefixes(executable: Path) -> list[Path]:
    """Installation prefixes a resolved executable needs to read.

    A venv's ``bin/python`` is a symlink to a base interpreter elsewhere: the venv
    (``pyvenv.cfg``, site-packages) and the base installation are both required.
    """

    def prefix(path: Path) -> Path:
        return path.parent.parent if path.parent.name == "bin" else path.parent

    linked = canonical(executable.parent) / executable.name
    return list(dict.fromkeys([prefix(linked), prefix(canonical(executable))]))


def python_prefixes(executable: str) -> list[Path]:
    """Real installation prefixes of a Python interpreter (``sys.prefix``, ``sys.base_prefix``).

    Runs the operator-selected interpreter once, isolated (``-I``) and outside the
    sandbox. Only the prefixes are re-allowed, not every ``sys.path`` entry: an
    editable install of the project would otherwise expose the original project
    folder. Returns an empty list for other executables or when the probe fails.
    """
    if not Path(executable).name.startswith("python"):
        return []
    probe = (
        "import json, os, sys; print(json.dumps([os.path.realpath(p) for p in "
        "(sys.prefix, sys.base_prefix)]))"
    )
    try:
        result = subprocess.run(
            [executable, "-I", "-c", probe],
            capture_output=True,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            timeout=30,
            check=False,
        )
        paths = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []
    if not isinstance(paths, list):
        return []
    return [Path(path) for path in paths if isinstance(path, str) and os.path.isdir(path)]


def readable_without_private(paths: list[Path], private: list[Path]) -> list[Path]:
    """Drop paths that would re-expose a private root or one of its ancestors.

    Paths inside the home directory remain allowed (for example an editable install
    under ``~/code``); Metis state, the experiment's siblings and broad ancestors do not.
    """
    home = canonical(Path.home())
    kept = []
    for path in paths:
        if any(root == path or root.is_relative_to(path) for root in private):
            continue
        if any(path.is_relative_to(root) for root in private if root != home):
            continue
        kept.append(path)
    return list(dict.fromkeys(kept))


def protected_paths(workspace: Path, relatives: list[str]) -> list[Path]:
    """Protected files plus their parent directories inside the workspace.

    Denying writes on the parents prevents renaming a directory to swap a nested
    protected file; creating other files inside those directories stays allowed.
    """
    paths: list[Path] = []
    for relative in relatives:
        parts = Path(relative).parts
        paths += [workspace.joinpath(*parts[:index]) for index in range(1, len(parts) + 1)]
    return list(dict.fromkeys(paths))


def seatbelt_command(tool: str, argv: list[str], paths: SandboxPaths) -> list[str]:
    """``sandbox-exec`` argv with a deny-by-default profile and parameterized paths."""
    params: list[str] = []

    def param(prefix: str, values: list[Path], form: str = "subpath") -> str:
        clauses = []
        for index, value in enumerate(values):
            text = str(value)
            if "\x00" in text or "\n" in text:
                raise ExecutionError("Sandbox paths cannot contain control characters")
            name = f"{prefix}{index}"
            params.extend(["-D", f"{name}={text}"])
            clauses.append(f'({form} (param "{name}"))')
        return " ".join(clauses)

    hidden = param("HIDE", [*map(Path, _MAC_HIDDEN), *paths.hidden])
    readable = param("READ", [paths.workspace, paths.private_tmp, *paths.readable])
    writable = param("WRITE", [paths.workspace, paths.private_tmp])
    # The workspace directory itself cannot be renamed, removed or replaced, so trusted
    # code that later reads it sees the same directory; files inside stay writable.
    protected = param("PROTECT", [paths.workspace, *paths.protected], "literal")
    tmp = param("SOCKET", [paths.private_tmp])
    services = " ".join(f'(global-name "{name}")' for name in _MACH_SERVICES)
    rules = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec process-fork)",
        "(allow signal (target same-sandbox))",
        "(allow process-info* (target same-sandbox))",
        "(allow sysctl-read)",
        "(allow ipc-posix-sem)",
        f'(allow ipc-posix-shm* (ipc-posix-name-regex #"{_SHM_NAMES}"))',
        # Apple-silicon Metal (MPS) needs its GPU user client and the shader compiler.
        '(allow iokit-open (iokit-registry-entry-class "RootDomainUserClient")'
        ' (iokit-user-client-class "AGXDeviceUserClient"))',
        f"(allow mach-lookup {services})",
        "(allow file-read*)",
        f"(deny file-read* {hidden})",
        # realpath() and exec may stat hidden parent directories and follow symlinks
        # (such as a venv's interpreter link); file contents stay unreadable.
        "(allow file-read-metadata (vnode-type DIRECTORY) (vnode-type SYMLINK))",
        f"(allow file-read* {readable})",
        f"(allow file-write* {writable})",
        '(allow file-write-data (literal "/dev/null") (literal "/dev/zero"))',
        # Local sockets (PyTorch's shared-memory manager) only inside the private directory.
        f"(allow network-bind network-outbound (local unix-socket {tmp}))",
        f"(allow network-outbound (remote unix-socket {tmp}))",
    ]
    if protected:
        rules.append(f"(deny file-write* {protected})")
    return [tool, "-p", "\n".join(rules), *params, *argv]


def bubblewrap_command(tool: str, argv: list[str], paths: SandboxPaths) -> list[str]:
    """``bwrap`` argv: host root read-only, private locations hidden, no network.

    Mount order matters: later binds are placed on top of earlier tmpfs mounts, so
    the workspace and environment remain visible inside hidden parents.
    """
    command = [
        tool,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--cap-drop",
        "ALL",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
    ]
    for hidden in [*map(Path, _LINUX_HIDDEN), *paths.hidden]:
        if hidden.is_dir():
            command += ["--tmpfs", str(hidden)]
    for device in paths.gpu_devices:
        command += ["--dev-bind", str(device), str(device)]
    for readable in paths.readable:
        command += ["--ro-bind", str(readable), str(readable)]
    command += ["--bind", str(paths.workspace), str(paths.workspace)]
    command += ["--bind", str(paths.private_tmp), str(paths.private_tmp)]
    for protected in paths.protected:
        command += ["--ro-bind", str(protected), str(protected)]
    command += ["--chdir", str(paths.workspace), "--", *argv]
    return command


def nvidia_devices() -> list[Path]:
    """NVIDIA device nodes needed for CUDA inside a bubblewrap sandbox."""
    found = [Path("/dev") / name for name in ("nvidiactl", "nvidia-uvm", "nvidia-uvm-tools")]
    found += sorted(Path("/dev").glob("nvidia[0-9]*"))
    caps = Path("/dev/nvidia-caps")
    return [path for path in [*found, caps] if path.exists()]


def podman_mode(info_text: str) -> dict[str, object]:
    """Parse ``podman info --format json`` into rootless mode and cgroup facts."""
    try:
        host = json.loads(info_text)["host"]
        return {
            "rootless": bool(host["security"]["rootless"]),
            "cgroup_version": str(host.get("cgroupVersion", "")),
            "controllers": sorted(map(str, host.get("cgroupControllers") or [])),
        }
    except (ValueError, KeyError, TypeError):
        raise ExecutionError(
            "Podman is unavailable; start it (on macOS: podman machine start)"
        ) from None


def podman_limits_problem(mode: dict[str, object]) -> str:
    """Why rootless Podman cannot enforce the configured limits, or an empty string.

    Rootless Podman on cgroup v1 drops CPU, memory and process limits with only a
    warning; without delegated controllers the run fails later.
    """
    controllers = mode.get("controllers")
    if mode.get("rootless") and (
        mode.get("cgroup_version") != "v2"
        or not isinstance(controllers, list)
        or not {"cpu", "memory", "pids"} <= set(controllers)
    ):
        return (
            "Rootless Podman cannot enforce CPU, memory and process limits here: it needs "
            "cgroups v2 with cpu, memory and pids delegated to your user. Ask the "
            "administrator to delegate them, or choose Docker or Apptainer."
        )
    return ""


_IMAGE_URI = re.compile(r"(?:docker|oras|library)://[A-Za-z0-9][A-Za-z0-9_./:@+-]*")


def validate_apptainer_image(image: str) -> None:
    if not image:
        return
    if _IMAGE_URI.fullmatch(image):
        return
    path = Path(image)
    if not path.is_absolute() or any(char in image for char in ",:\x00\n"):
        raise ExecutionError(
            "Apptainer image must be an absolute SIF path without commas or colons, or a docker://, oras:// or library:// reference"
        )


def environment_bin(environment_dir: str) -> Path | None:
    """The executable directory of a configured Python environment prefix."""
    if not environment_dir:
        return None
    root = Path(environment_dir)
    if not root.is_absolute() or any(char in environment_dir for char in "\x00\n"):
        raise ExecutionError("Execution environment must be an absolute directory path")
    return root / ("Scripts" if os.name == "nt" else "bin")


def resolve_native(name: str, environment_dir: str) -> str:
    """Resolve an allowed bare executable, preferring the configured environment."""
    directory = environment_bin(environment_dir)
    if directory is not None:
        if not directory.is_dir():
            raise ExecutionError(f"Execution environment has no executable directory: {directory}")
        found = shutil.which(name, path=str(directory))
        if found:
            return found
    found = shutil.which(name)
    if not found:
        raise ExecutionError(f"Execution tool is unavailable: {name}")
    return found


def environment_variables(environment_dir: str) -> dict[str, str]:
    """Activation variables a venv or conda prefix expects; activation scripts are not run."""
    if not environment_dir:
        return {}
    root = Path(environment_dir)
    if (root / "conda-meta").is_dir():
        return {"CONDA_PREFIX": str(root)}
    if (root / "pyvenv.cfg").is_file():
        return {"VIRTUAL_ENV": str(root)}
    return {}


_DIGESTS: dict[tuple[int, int, int, int], str] = {}


def image_digest(image: str) -> str | None:
    """SHA-256 of a local SIF image, cached per file identity; None for registry URIs.

    A registry reference is resolved by Apptainer at run time and recorded as given.
    """
    if not image or _IMAGE_URI.fullmatch(image):
        return None
    try:
        info = os.stat(image)
    except OSError:
        raise ExecutionError(f"Apptainer image is unavailable: {image}") from None
    key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if key not in _DIGESTS:
        digest = hashlib.sha256()
        with open(image, "rb") as handle:
            while chunk := handle.read(4 * 1024 * 1024):
                digest.update(chunk)
        _DIGESTS[key] = digest.hexdigest()
    return _DIGESTS[key]


def _bind(source: Path | str, target: str, *, readonly: bool) -> list[str]:
    text = f"{source}:{target}"
    if any(char in str(source) + target for char in ",:\x00\n"):
        raise ExecutionError("Apptainer bind paths cannot contain commas, colons or newlines")
    return ["--bind", text + (":ro" if readonly else "")]


def apptainer_command(
    tool: str,
    image: str,
    argv: list[str],
    *,
    workspace: Path,
    snapshot: Path | None,
    protected: list[str],
    mounts: list[dict[str, str]],
    env: dict[str, str],
    gpus: int,
) -> tuple[list[str], dict[str, str]]:
    """``apptainer exec`` argv plus the host variables that carry the workload environment.

    The container gets a contained filesystem, PID and IPC namespace and a clean
    environment; only the workspace is writable. Workload variables travel as
    ``APPTAINERENV_*`` (``SINGULARITYENV_*`` for SingularityCE) host variables, which
    avoids the comma parsing of ``--env`` and the shell evaluation of ``--env-file``.
    Requires Apptainer >= 1.1 or SingularityCE >= 3.10 for ``--no-eval``. Resource limits
    come from Slurm; unprivileged ``--cpus/--memory`` need a systemd user session.
    """
    command = [
        tool,
        "exec",
        "--containall",
        "--cleanenv",
        "--no-home",
        # Never shell-evaluate arguments or variables inside the container.
        "--no-eval",
        # Unprivileged users may create only the empty "none" network namespace.
        "--net",
        "--network",
        "none",
        "--pwd",
        "/workspace",
        *_bind(workspace, "/workspace", readonly=False),
    ]
    if snapshot is not None:
        command += _bind(snapshot, "/autoresearch-protected", readonly=True)
        for relative in protected:
            command += _bind(snapshot / relative, f"/workspace/{relative}", readonly=True)
    for mount in mounts:
        command += _bind(mount["source"], mount["target"], readonly=True)
    if gpus:
        command.append("--nv")
    prefix = "SINGULARITYENV_" if Path(tool).name == "singularity" else "APPTAINERENV_"
    return [*command, image, *argv], {prefix + name: value for name, value in env.items()}


def workspace_identity(path: Path) -> tuple[int, int]:
    """Device and inode of a real (non-symlink) workspace directory."""
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode):
        raise ExecutionError("Experiment workspace must be a directory")
    return info.st_dev, info.st_ino


class _CloneTimeout(Exception):
    pass


def _clone_file(source: int, directory: int, name: str, deadline: float) -> None:
    """Copy-on-write clone of an open file on APFS, else a streamed copy."""
    if sys.platform == "darwin":
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        clone = libc.fclonefileat
        clone.restype = ctypes.c_int
        clone.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        if clone(source, directory, os.fsencode(name), 0) == 0:
            return
    target = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    with os.fdopen(target, "wb") as output:
        while chunk := os.read(source, 4 * 1024 * 1024):
            if time.monotonic() > deadline:
                raise _CloneTimeout
            output.write(chunk)


def _clone_directory(source: int, target: int, deadline: float, depth: int) -> None:
    if depth > 256:
        raise ExecutionError("Workspace directories are nested too deeply to copy")
    for entry in os.scandir(source):
        if time.monotonic() > deadline:
            raise _CloneTimeout
        name = entry.name
        mode = os.stat(name, dir_fd=source, follow_symlinks=False).st_mode
        if stat.S_ISLNK(mode):
            # Links are recreated, never followed by this trusted copy.
            os.symlink(os.readlink(name, dir_fd=source), name, dir_fd=target)
        elif stat.S_ISDIR(mode):
            os.mkdir(name, 0o700, dir_fd=target)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source)
            try:
                destination = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=target
                )
                try:
                    _clone_directory(child, destination, deadline, depth + 1)
                finally:
                    os.close(destination)
            finally:
                os.close(child)
        elif stat.S_ISREG(mode):
            try:
                descriptor = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source
                )
            except OSError:
                continue  # replaced by a link or removed since listing
            try:
                if stat.S_ISREG(os.fstat(descriptor).st_mode):
                    _clone_file(descriptor, target, name, deadline)
            finally:
                os.close(descriptor)
        # Sockets, FIFOs and devices are not copied.


def clone_workspace(
    source: Path, identity: tuple[int, int], destination: Path, deadline: float
) -> str:
    """Copy a workspace through no-follow descriptors; an empty string means success.

    The source must still be the directory recorded before the workload ran. Every
    component is opened without following symlinks, so a process that swaps files or
    links during the copy cannot make trusted code read outside the workspace.
    """
    try:
        root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return "The workspace changed before evaluation"
    try:
        info = os.fstat(root)
        if (info.st_dev, info.st_ino) != identity:
            return "The workspace was replaced before evaluation"
        target = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _clone_directory(root, target, deadline, 0)
        finally:
            os.close(target)
    except _CloneTimeout:
        return "Evaluation time limit reached while copying the workspace"
    except (OSError, ExecutionError) as error:
        return f"The workspace could not be copied for isolated evaluation: {error}"
    finally:
        os.close(root)
    return ""
