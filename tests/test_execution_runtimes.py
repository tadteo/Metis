"""Podman, Apptainer, native sandbox and Python-environment selection for experiments."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from autoresearch import isolation
from autoresearch.contracts import ExecutionConfig, ExperimentSpec
from autoresearch.execution import ExecutionError, Executor, _Process

PROTECTED = {"evaluator_argv": ["python3", "evaluate.py"], "protected_files": ["evaluate.py"]}


def spec(root: Path, code: str = "print('run')", **kwargs: Any) -> ExperimentSpec:
    return ExperimentSpec(
        id="runtime-experiment",
        kind="subset",
        workspace=str(root),
        argv=["python3", "-c", code],
        **kwargs,
    )


def fake_run(
    calls: list[tuple[list[str], dict[str, Any]]], root: Path, stdout: str = ""
) -> Callable[..., _Process]:
    def run(argv: list[str], **kwargs: Any) -> _Process:
        calls.append((argv, kwargs))
        (root / "metrics.json").write_text('{"score":1}')
        return _Process(stdout, "", 0, 0.1)

    return run


def podman_info(rootless: bool, version: str = "v2", controllers: tuple[str, ...] = ()) -> str:
    return json.dumps(
        {
            "host": {
                "security": {"rootless": rootless},
                "cgroupVersion": version,
                "cgroupControllers": list(controllers or ("cpu", "memory", "pids")),
            }
        }
    )


def podman_run(
    calls: list[tuple[list[str], dict[str, Any]]], root: Path, info: str
) -> Callable[..., _Process]:
    def run(argv: list[str], **kwargs: Any) -> _Process:
        calls.append((argv, kwargs))
        if argv[1:2] == ["info"]:
            return _Process(info, "", 0, 0.1)
        (root / "metrics.json").write_text('{"score":1}')
        return _Process("a" * 64, "", 0, 0.1)

    return run


@pytest.mark.parametrize("rootless", [True, False])
def test_podman_matches_docker_isolation_and_records_bare_image_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rootless: bool
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "never-inherit-this")
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(
        "autoresearch.execution._run", podman_run(calls, tmp_path, podman_info(rootless))
    )
    result = Executor(ExecutionConfig(backend="podman", gpus=2)).run(spec(tmp_path))
    assert result.status == "completed"
    assert calls[0][0] == ["/usr/bin/podman", "info", "--format", "json"]
    command, options = calls[1]
    assert command[:2] == ["/usr/bin/podman", "run"]
    assert ("--userns" in command) is rootless
    if rootless:
        assert command[command.index("--userns") + 1] == "keep-id"
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--read-only-tmpfs=false" in command
    assert "--init=false" in command
    assert any(part.endswith(",notmpcopyup") for part in command)
    # Podman reads --gpus N as an index, so request devices explicitly.
    assert "--gpus" not in command
    devices = [command[i + 1] for i, part in enumerate(command) if part == "--device"]
    assert devices == ["nvidia.com/gpu=0", "nvidia.com/gpu=1"]
    assert "XAI_API_KEY" not in options["env"] and "HOME" in options["env"]
    assert calls[2][0][:3] == ["/usr/bin/podman", "image", "inspect"]
    assert calls[-1][0][1:3] == ["rm", "--force"]
    environment = result.provenance["environment"]
    assert environment["resolved_image_id"] == "sha256:" + "a" * 64
    assert environment["podman_rootless"] is rootless
    assert result.provenance["data_provenance"]["mounts_applied"] is True


@pytest.mark.parametrize(
    "info",
    [podman_info(True, "v1"), podman_info(True, "v2", ("memory", "pids")), "not json"],
)
def test_podman_refuses_limits_it_cannot_enforce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, info: str
) -> None:
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr("autoresearch.execution._run", podman_run(calls, tmp_path, info))
    with pytest.raises(ExecutionError, match="Podman"):
        Executor(ExecutionConfig(backend="podman")).run(spec(tmp_path))
    assert all(call[0][1] != "run" for call in calls)


def test_apptainer_contains_environment_and_binds_protocol_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, dataset = tmp_path / "work", tmp_path / "dataset"
    workspace.mkdir()
    dataset.mkdir()
    (dataset / "values.txt").write_text("1 2 3")
    (workspace / "evaluate.py").write_text("pass")
    image = tmp_path / "project.sif"
    image.write_bytes(b"synthetic image")
    monkeypatch.setenv("XAI_API_KEY", "never-inherit-this")
    monkeypatch.setattr(Executor, "_apptainer_tool", lambda self: "/usr/bin/apptainer")
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr("autoresearch.execution._run", fake_run(calls, workspace))
    executor = Executor(
        ExecutionConfig(
            backend="apptainer",
            apptainer_image=str(image),
            gpus=1,
            readonly_mounts={str(dataset): "/data/values"},
        )
    )
    result = executor.run(spec(workspace, metadata=PROTECTED, seed=7))
    assert result.status == "completed"
    command, options = calls[0]
    assert command[:3] == ["/usr/bin/apptainer", "exec", "--containall"]
    assert {"--cleanenv", "--no-home", "--no-eval", "--nv"} <= set(command)
    assert command[command.index("--network") + 1] == "none"
    binds = [command[i + 1] for i, part in enumerate(command) if part == "--bind"]
    assert f"{workspace}:/workspace" in binds
    assert any(bind.endswith(":/autoresearch-protected:ro") for bind in binds)
    assert any(bind.endswith(":/workspace/evaluate.py:ro") for bind in binds)
    assert f"{dataset}:/data/values:ro" in binds
    assert command[command.index(str(image)) + 1 :][:1] == ["python3"]
    # Workload variables travel through the runtime, never as argv or provider keys.
    assert options["env"]["APPTAINERENV_AUTORESEARCH_SEED"] == "7"
    assert all("AUTORESEARCH_SEED" not in part for part in command)
    assert "XAI_API_KEY" not in options["env"]
    runner = json.loads((workspace / ".autoresearch-slurm-config.json").read_text())
    assert runner["evaluator_argv"] == ["python3", "/autoresearch-protected/evaluate.py"]
    provenance = result.provenance
    assert provenance["evaluator_isolated"] is True
    assert provenance["data_provenance"]["mount_access"] == "container_target"
    expected = hashlib.sha256(b"synthetic image").hexdigest()
    assert provenance["environment"]["resolved_image_id"] == "sha256:" + expected


@pytest.mark.parametrize(
    "config,message",
    [
        ({"backend": "apptainer"}, "apptainer_image"),
        ({"backend": "slurm", "slurm_container": "apptainer"}, "apptainer_image"),
    ],
)
def test_apptainer_requires_an_image(tmp_path: Path, config: dict[str, Any], message: str) -> None:
    with pytest.raises(ExecutionError, match=message):
        Executor(ExecutionConfig(**config)).run(spec(tmp_path))


@pytest.mark.parametrize(
    "image", ["relative.sif", "/images/a:b.sif", "http://example.org/x", "docker://"]
)
def test_apptainer_image_references_are_validated(image: str) -> None:
    with pytest.raises(ExecutionError, match="Apptainer image"):
        Executor(ExecutionConfig(backend="apptainer", apptainer_image=image))


def test_apptainer_rejects_bind_separators_in_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "with:colon"
    workspace.mkdir()
    executor = Executor(
        ExecutionConfig(backend="apptainer", apptainer_image="docker://python:3.11")
    )
    with pytest.raises(ExecutionError, match="commas or colons"):
        executor.run(spec(workspace))


def test_slurm_job_runs_trusted_runner_inside_apptainer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "evaluate.py").write_text("pass")
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    monkeypatch.setattr(Executor, "_apptainer_tool", lambda self: "/usr/bin/apptainer")
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> _Process:
        calls.append(argv)
        return _Process("42\n", "", 0, 0.1)

    monkeypatch.setattr("autoresearch.execution._run", run)
    executor = Executor(
        ExecutionConfig(
            backend="slurm",
            slurm_container="apptainer",
            apptainer_image="docker://python:3.11-slim",
            gpus=1,
        )
    )
    pending = executor.run(spec(tmp_path, metadata=PROTECTED))
    assert pending.status == "pending" and pending.job_id == "42"
    script = (tmp_path / ".autoresearch-job.sh").read_text()
    assert "/usr/bin/apptainer exec --containall" in script
    assert "--nv" in script and "docker://python:3.11-slim python3" in script
    assert "/workspace/.autoresearch-slurm-runner.py" in script
    assert "APPTAINERENV_PYTHONHASHSEED=0" in script
    assert (
        '${CUDA_VISIBLE_DEVICES+"APPTAINERENV_CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"}'
        in script
    )
    assert f"{tmp_path}:/workspace" in script
    assert calls[0][0] == "/usr/bin/sbatch" and calls[0][calls[0].index("--gpus") + 1] == "1"
    runner = json.loads((tmp_path / ".autoresearch-slurm-config.json").read_text())
    assert runner["evaluator_argv"] == ["python3", "/autoresearch-protected/evaluate.py"]
    assert pending.provenance["evaluator_isolated"] is True


def test_slurm_job_uses_configured_python_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = tmp_path / "env"
    (environment / "conda-meta").mkdir(parents=True)
    workspace = tmp_path / "work"
    workspace.mkdir()
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    monkeypatch.setattr(
        "autoresearch.execution._run", lambda argv, **kwargs: _Process("7", "", 0, 0.1)
    )
    executor = Executor(ExecutionConfig(backend="slurm", environment_dir=str(environment)))
    pending = executor.run(spec(workspace))
    script = (workspace / ".autoresearch-job.sh").read_text()
    assert f"PATH={environment}/bin:" in script
    assert f"CONDA_PREFIX={environment}" in script
    assert pending.provenance["environment"]["environment_dir"] == str(environment)


def test_slurm_job_script_forwards_scheduler_gpu_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the generated job script as a compute node would, without a scheduler."""
    environment = fake_environment(tmp_path)
    workspace = tmp_path / "work"
    workspace.mkdir()
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    monkeypatch.setattr(
        "autoresearch.execution._run", lambda argv, **kwargs: _Process("9", "", 0, 0.1)
    )
    code = (
        "import json, os; json.dump({'visible': len(os.environ['CUDA_VISIBLE_DEVICES']"
        ".split(','))}, open('metrics.json', 'w'))"
    )
    executor = Executor(ExecutionConfig(backend="slurm", gpus=2, environment_dir=str(environment)))
    executor.run(spec(workspace, code))
    job = workspace / ".autoresearch-job.sh"
    completed = subprocess.run(
        ["/bin/sh", str(job)],
        cwd=workspace,
        env={"PATH": os.defpath, "CUDA_VISIBLE_DEVICES": "0,1", "XAI_API_KEY": "never"},
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads((workspace / "metrics.json").read_text()) == {"visible": 2}
    assert "XAI_API_KEY" not in job.read_text()


def fake_environment(root: Path) -> Path:
    """A conda-style prefix whose python3 links to the test interpreter."""
    environment = root / "project-env"
    (environment / "bin").mkdir(parents=True)
    (environment / "conda-meta").mkdir()
    os.symlink(sys.executable, environment / "bin" / "python3")
    return environment


def test_environment_activation_variables(tmp_path: Path) -> None:
    venv, conda = tmp_path / "venv", tmp_path / "conda"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (conda / "conda-meta").mkdir(parents=True)
    assert isolation.environment_variables(str(venv)) == {"VIRTUAL_ENV": str(venv)}
    assert isolation.environment_variables(str(conda)) == {"CONDA_PREFIX": str(conda)}
    assert isolation.environment_variables("") == {}


def test_local_runs_with_the_configured_environment(tmp_path: Path) -> None:
    environment = fake_environment(tmp_path)
    workspace = tmp_path / "work"
    workspace.mkdir()
    expected_prefix, expected_bin = str(environment), str(environment / "bin")
    code = (
        "import json, os; json.dump({"
        f"'prefix': int(os.environ['CONDA_PREFIX'] == {expected_prefix!r}), "
        f"'first': int(os.environ['PATH'].split(os.pathsep)[0] == {expected_bin!r})"
        "}, open('metrics.json', 'w'))"
    )
    executor = Executor(
        ExecutionConfig(backend="local", allow_local=True, environment_dir=str(environment))
    )
    result = executor.run(spec(workspace, code))
    assert result.status == "completed", result.stderr
    assert result.metrics == {"prefix": 1, "first": 1}
    assert result.provenance["executable"] == str(environment / "bin" / "python3")


def test_environment_without_executables_fails_clearly(tmp_path: Path) -> None:
    executor = Executor(
        ExecutionConfig(backend="local", allow_local=True, environment_dir=str(tmp_path / "none"))
    )
    with pytest.raises(ExecutionError, match="no executable directory"):
        executor.run(spec(tmp_path))
    with pytest.raises(ExecutionError, match="absolute"):
        Executor(ExecutionConfig(environment_dir="relative/env"))


def test_seatbelt_profile_receives_paths_only_as_parameters(tmp_path: Path) -> None:
    hostile = tmp_path / 'ws") (allow default) ("'
    paths = isolation.SandboxPaths(
        workspace=hostile, private_tmp=tmp_path / "tmp", protected=[hostile / "evaluate.py"]
    )
    command = isolation.seatbelt_command("/usr/bin/sandbox-exec", ["python3"], paths)
    profile = command[2]
    assert command[1] == "-p" and "(deny default)" in profile
    assert str(hostile) not in profile and "(allow default)" not in profile
    assert f"WRITE0={hostile}" in command
    # Protected files are fully write-denied; the workspace itself cannot be renamed or replaced.
    assert f"ROOT0={hostile}" in command and f"PROTECT0={hostile / 'evaluate.py'}" in command
    assert '(deny file-write* (literal (param "PROTECT0")))' in profile
    assert '(deny file-write-create file-write-unlink (literal (param "ROOT0")))' in profile
    # Only Unix sockets inside the private directory; no IP networking rule exists.
    network = [line for line in profile.splitlines() if "network" in line]
    assert network and all('(param "SOCKET0")' in line for line in network)
    assert "(allow iokit-open)" not in profile and "(allow mach-lookup)" not in profile
    assert command[-1] == "python3"


def test_sandbox_allows_import_paths_without_reexposing_private_roots(tmp_path: Path) -> None:
    home = isolation.canonical(Path.home())
    state = isolation.canonical(tmp_path) / "state"
    private = [home, state, state / "runs" / "r" / "experiments"]
    editable = home / "code" / "library"
    kept = isolation.readable_without_private(
        [editable, home, home.parent, state / "runs" / "r" / "notes", Path("/usr/lib")], private
    )
    assert kept == [editable, Path("/usr/lib")]
    paths = isolation.python_prefixes(sys.executable)
    assert isolation.canonical(Path(sys.prefix)) in paths
    # Only installation prefixes: an editable project on sys.path is not re-exposed.
    assert all(
        isolation.canonical(Path(sys.prefix)) == path
        or path == isolation.canonical(Path(sys.base_prefix))
        for path in paths
    )
    assert isolation.python_prefixes("/usr/bin/Rscript") == []


def test_bubblewrap_hides_private_locations_before_rebinding_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "state" / "runs" / "abcdefabcdef" / "experiments" / "e1"
    workspace.mkdir(parents=True)
    (workspace / "evaluate.py").write_text("pass")
    monkeypatch.setattr(isolation.sys, "platform", "linux")
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr("autoresearch.execution._run", fake_run(calls, workspace))
    result = Executor(ExecutionConfig(backend="sandbox")).run(spec(workspace, metadata=PROTECTED))
    assert result.status == "completed"
    command, options = calls[0]
    assert command[0] == "/usr/bin/bwrap"
    assert {"--unshare-all", "--die-with-parent", "--new-session"} <= set(command)
    real = isolation.canonical(workspace)
    state = str(isolation.canonical(tmp_path / "state"))
    tmpfs = [command[i + 1] for i, part in enumerate(command) if part == "--tmpfs"]
    assert state in tmpfs
    bind = command.index("--bind")
    assert command[bind + 1 : bind + 3] == [str(real), str(real)]
    assert bind > max(i for i, part in enumerate(command) if part == "--tmpfs")
    protected = command.index(str(real / "evaluate.py")) - 1
    assert command[protected] == "--ro-bind" and protected > bind
    assert command[command.index("--chdir") + 1] == str(real)
    assert options["env"]["HOME"].startswith(options["env"]["TMPDIR"])
    assert result.provenance["sandbox"]["kind"] == "bubblewrap"
    assert result.provenance["evaluator_isolated"] is True
    assert result.provenance["data_provenance"]["mount_access"] == "host_path_read_only"
    assert not list(workspace.parent.glob(".autoresearch-sandbox-*"))


@pytest.mark.skipif(
    sys.platform != "darwin" or not shutil.which("sandbox-exec"), reason="macOS Seatbelt only"
)
def test_seatbelt_sandbox_denies_network_private_reads_and_outside_writes(
    tmp_path: Path,
) -> None:
    state = isolation.canonical(tmp_path) / "state"
    workspace = state / "runs" / "abcdefabcdef" / "experiments" / "e1"
    workspace.mkdir(parents=True)
    (state / "research.sqlite3").write_text("private record")
    sibling = workspace.parent / "e0"
    sibling.mkdir()
    (sibling / "notes.txt").write_text("another experiment")
    (workspace / "evaluate.py").write_text(
        "import json\nopen('metrics.json', 'w').write(json.dumps({'score': 1}))\n"
    )
    outside = state.parent / "escape.txt"
    probe = """
import json, socket, sys
results = {}
def attempt(name, action):
    try:
        action()
        results[name] = 'allowed'
    except OSError:
        results[name] = 'denied'
attempt('state', lambda: open(sys.argv[1]).read())
attempt('sibling', lambda: open(sys.argv[2]).read())
attempt('outside', lambda: open(sys.argv[3], 'w').write('x'))
attempt('protected', lambda: open('evaluate.py', 'a').write('#'))
attempt('network', lambda: socket.create_connection(('127.0.0.1', int(sys.argv[4])), timeout=2))
attempt('workspace', lambda: open('result.txt', 'w').write('ok'))
json.dump(results, open('probe.json', 'w'))
"""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    try:
        experiment = ExperimentSpec(
            id="sandboxed",
            kind="subset",
            workspace=str(workspace),
            argv=[
                "python3",
                "-c",
                probe,
                str(state / "research.sqlite3"),
                str(sibling / "notes.txt"),
                str(outside),
                str(listener.getsockname()[1]),
            ],
            metadata=PROTECTED,
            timeout_seconds=60,
        )
        result = Executor(ExecutionConfig(backend="sandbox")).run(experiment)
    finally:
        listener.close()
    assert result.status == "completed", result.stderr
    assert result.metrics == {"score": 1}
    assert json.loads((workspace / "probe.json").read_text()) == {
        "state": "denied",
        "sibling": "denied",
        "outside": "denied",
        "protected": "denied",
        "network": "denied",
        "workspace": "allowed",
    }
    assert not outside.exists()
    assert result.provenance["sandbox"]["kind"] == "seatbelt"


def test_docker_client_environment_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr("autoresearch.execution._run", fake_run(calls, tmp_path))
    Executor(ExecutionConfig()).run(spec(tmp_path))
    environment = calls[0][1]["env"]
    assert environment["PATH"] == os.defpath
    assert "XDG_RUNTIME_DIR" not in environment and environment["HOME"] == str(Path.home())


def test_store_directories_are_hidden_from_native_sandboxes(tmp_path: Path) -> None:
    from autoresearch.store import Store

    database = tmp_path / "elsewhere" / "database"
    Store(tmp_path / "state", db_dir=database)
    workspace = tmp_path / "unrelated" / "work"
    workspace.mkdir(parents=True)
    roots = isolation.private_roots(isolation.canonical(workspace))
    assert isolation.canonical(database) in roots
    assert isolation.canonical(tmp_path / "state") in roots


def test_sandbox_rejects_dataset_inside_metis_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    workspace = state / "runs" / "abcdefabcdef" / "experiments" / "e1"
    workspace.mkdir(parents=True)
    dataset = state / "runs" / "abcdefabcdef" / "data"
    dataset.mkdir()
    (dataset / "values.txt").write_text("1")
    monkeypatch.setattr(isolation.sys, "platform", "linux")
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)
    executor = Executor(
        ExecutionConfig(backend="sandbox", readonly_mounts={str(dataset): "/data/values"})
    )
    with pytest.raises(ExecutionError, match="overlaps Metis state"):
        executor.run(spec(workspace))


RUNNER = Path(__file__).parents[1] / "src/autoresearch/assets/programs/slurm_runner.py"


def _runner_module() -> Any:
    import importlib.util

    loader = importlib.util.spec_from_file_location("metis_runner_under_test", RUNNER)
    assert loader is not None and loader.loader is not None
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def test_runner_signatures_run_on_older_cluster_pythons() -> None:
    """Signature annotations are evaluated at definition time on Python < 3.10."""
    import ast

    source = RUNNER.read_text()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef):
            arguments = node.args
            every = [
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                arguments.vararg,
                arguments.kwarg,
            ]
            annotations = [arg.annotation for arg in every if arg is not None] + [node.returns]
            for annotation in annotations:
                if annotation is None or isinstance(annotation, ast.Constant):
                    continue
                assert not isinstance(annotation, (ast.BinOp, ast.Subscript)), node.name
    assert "is_relative_to" not in source and "missing_ok" not in source
    older = Path("/usr/bin/python3")
    if older.exists():
        completed = subprocess.run(
            [
                str(older),
                "-c",
                "import sys; compile(open(sys.argv[1]).read(), 'r', 'exec')",
                str(RUNNER),
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    "pid,parent,expected",
    [
        (1, 0, True),  # Docker/Podman with --init=false: the runner is the namespace init
        (2, 1, True),  # bubblewrap or an Apptainer init shim
        (7, 1, False),  # a later process (for example under docker --init)
        (2, 3, False),
        (4321, 1, False),  # an ordinary host process
    ],
)
def test_runner_isolates_only_as_first_process_of_a_namespace(
    pid: int, parent: int, expected: bool
) -> None:
    assert _runner_module()._private_namespace(pid, parent) is expected


def test_runner_refuses_evaluator_isolation_outside_a_private_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-process with os.kill replaced, so a regression can never signal real processes."""
    runner = _runner_module()
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(runner.os, "kill", lambda pid, signum: signals.append((pid, signum)))
    with pytest.raises(SystemExit) as stopped:
        runner._end_workload_processes()  # this test process is not a namespace init
    assert stopped.value.code == 125 and signals == []
    monkeypatch.setattr(runner.os, "getpid", lambda: 1)
    monkeypatch.setattr(runner.os, "getppid", lambda: 0)
    monkeypatch.setattr(runner, "_remaining_processes", lambda: [])
    runner._end_workload_processes()
    assert signals == [(-1, 9)]


def test_trusted_copy_never_follows_workspace_links(tmp_path: Path) -> None:
    import time as clock

    workspace, hidden, copy = tmp_path / "work", tmp_path / "hidden", tmp_path / "copy"
    for directory in (workspace / "nested", hidden, copy):
        directory.mkdir(parents=True)
    (hidden / "secret.txt").write_text("synthetic hidden")
    (workspace / "nested" / "result.txt").write_text("42")
    (workspace / "link").symlink_to(hidden)
    (workspace / "file-link.txt").symlink_to(hidden / "secret.txt")
    identity = isolation.workspace_identity(workspace)
    deadline = clock.monotonic() + 30
    assert isolation.clone_workspace(workspace, identity, copy, deadline) == ""
    assert (copy / "nested" / "result.txt").read_text() == "42"
    assert (copy / "link").is_symlink() and (copy / "file-link.txt").is_symlink()
    assert not any(path.name == "secret.txt" and not path.is_symlink() for path in copy.rglob("*"))
    replaced = tmp_path / "replaced"
    replaced.mkdir()
    assert "replaced" in isolation.clone_workspace(replaced, identity, tmp_path / "x", deadline)
    later = tmp_path / "later"
    later.mkdir()
    expired = isolation.clone_workspace(workspace, identity, later, clock.monotonic() - 1)
    assert expired.startswith("Evaluation time limit")


def test_protected_inputs_are_restored_before_the_evaluator(tmp_path: Path) -> None:
    """A workload that swaps a nested protected input by renaming its directory."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "labels.txt").write_text("trusted")
    (tmp_path / "evaluate.py").write_text(
        "import json\n"
        "label = open('data/labels.txt').read()\n"
        "json.dump({'trusted': int(label == 'trusted')}, open('metrics.json', 'w'))\n"
    )
    code = (
        "import os; os.rename('data', 'moved'); os.mkdir('data'); "
        "open('data/labels.txt', 'w').write('forged')"
    )
    metadata = {
        "evaluator_argv": ["python3", "evaluate.py"],
        "protected_files": ["evaluate.py", "data/labels.txt"],
    }
    executor = Executor(ExecutionConfig(backend="local", allow_local=True))
    result = executor.run(spec(tmp_path, code, metadata=metadata))
    assert result.status == "completed", result.stderr
    assert result.metrics == {"trusted": 1}
    assert result.provenance["evaluator_isolation"] == "none"


@pytest.mark.skipif(
    not os.environ.get("AUTORESEARCH_DOCKER_TEST_IMAGE"),
    reason="Set AUTORESEARCH_DOCKER_TEST_IMAGE to a local image with python3",
)
def test_docker_ends_background_workload_before_evaluation(tmp_path: Path) -> None:
    """Live: a daemonized workload must not overwrite the evaluator's metrics."""
    _assert_background_process_cannot_forge(
        tmp_path,
        ExecutionConfig(docker_image=os.environ["AUTORESEARCH_DOCKER_TEST_IMAGE"]),
    )


DAEMON = """
import json, os, time
if os.fork():
    raise SystemExit(0)
os.setsid()
if os.fork():
    os._exit(0)
for _ in range(3000):
    try:
        if '"score": 0' in open('metrics.json').read():
            open('metrics.json', 'w').write(json.dumps({'score': 777}))
            break
    except OSError:
        pass
    time.sleep(0.002)
"""


def _assert_background_process_cannot_forge(root: Path, config: ExecutionConfig) -> None:
    (root / "evaluate.py").write_text(
        "import json, time\ntime.sleep(0.5)\n"
        "json.dump({'score': 0}, open('metrics.json', 'w'))\ntime.sleep(1)\n"
    )
    experiment = ExperimentSpec(
        id="background",
        kind="subset",
        workspace=str(root),
        argv=["python3", "-c", DAEMON],
        metadata=PROTECTED,
        timeout_seconds=60,
    )
    result = Executor(config).run(experiment)
    assert result.status == "completed", result.stderr
    assert result.metrics == {"score": 0}
    assert result.provenance["evaluator_isolated"] is True


@pytest.mark.skipif(
    sys.platform != "darwin" or not shutil.which("sandbox-exec"), reason="macOS Seatbelt only"
)
def test_seatbelt_evaluator_resists_background_processes_and_user_site(tmp_path: Path) -> None:
    experiments = isolation.canonical(tmp_path) / "state" / "runs" / "abcdefabcdef" / "experiments"
    background = experiments / "background"
    background.mkdir(parents=True)
    # Seatbelt cannot end the leftover process; the evaluator's separate copy is what holds.
    _assert_background_process_cannot_forge(background, ExecutionConfig(backend="sandbox"))
    workspace = experiments / "user-site"
    workspace.mkdir()
    (workspace / "evaluate.py").write_text(
        "import json\njson.dump({'score': 0}, open('metrics.json', 'w'))\n"
    )
    plant = (
        "import os, site; path = site.getusersitepackages(); os.makedirs(path, exist_ok=True); "
        "open(os.path.join(path, 'usercustomize.py'), 'w').write("
        "\"import atexit, json\\natexit.register(lambda: json.dump({'score': 999}, "
        "open('metrics.json', 'w')))\\n\")"
    )
    result = Executor(ExecutionConfig(backend="sandbox")).run(
        spec(workspace, plant, metadata=PROTECTED)
    )
    assert result.status == "completed", result.stderr
    assert result.metrics == {"score": 0}
    assert result.provenance["evaluator_isolation"] == "separate_sandbox_copy"
    assert json.loads((workspace / "metrics.json").read_text()) == {"score": 0}
    assert not list(workspace.parent.glob(".autoresearch-evaluation-*"))


@pytest.mark.skipif(
    sys.platform != "darwin" or not shutil.which("sandbox-exec"), reason="macOS Seatbelt only"
)
def test_seatbelt_workspace_cannot_be_renamed_but_stays_writable(tmp_path: Path) -> None:
    workspace = isolation.canonical(tmp_path) / "state" / "runs" / "abcdefabcdef" / "experiments"
    workspace = workspace / "e1"
    workspace.mkdir(parents=True)
    (workspace / "sub").mkdir()
    (workspace / "sub" / "check.py").write_text("ORIGINAL = True\n")
    (workspace / "evaluate.py").write_text(
        "import json\njson.dump({'score': 0}, open('metrics.json', 'w'))\n"
    )
    probe = (
        "import json, os\n"
        "results = {}\n"
        "def attempt(name, action):\n"
        "    try:\n"
        "        action(); results[name] = 'allowed'\n"
        "    except OSError:\n"
        "        results[name] = 'denied'\n"
        "attempt('rename_root', lambda: os.rename(os.getcwd(), os.path.join(os.environ['TMPDIR'], 'moved')))\n"
        "attempt('rename_protected_parent', lambda: os.rename('sub', 'sub2'))\n"
        "attempt('create_in_root', lambda: open('created.txt', 'w').write('ok'))\n"
        "attempt('create_in_protected_parent', lambda: open('sub/new.txt', 'w').write('ok'))\n"
        "attempt('touch_root', lambda: os.utime('.'))\n"
        "attempt('chmod_root', lambda: os.chmod('.', 0o700))\n"
        "import shutil, stat\n"
        "os.makedirs(os.path.join(os.environ['TMPDIR'], 'src', 'pkg'))\n"
        "open(os.path.join(os.environ['TMPDIR'], 'src', 'pkg', 'a.txt'), 'w').write('a')\n"
        "attempt('copytree_into_root', lambda: shutil.copytree(os.path.join(os.environ['TMPDIR'], 'src'), '.', dirs_exist_ok=True))\n"
        "open('locked.txt', 'w').write('x')\n"
        "attempt('immutable_file', lambda: os.chflags('locked.txt', stat.UF_IMMUTABLE))\n"
        "json.dump(results, open('probe.json', 'w'))\n"
    )
    metadata = {
        "evaluator_argv": ["python3", "evaluate.py"],
        "protected_files": ["evaluate.py", "sub/check.py"],
    }
    result = Executor(ExecutionConfig(backend="sandbox")).run(
        spec(workspace, probe, metadata=metadata)
    )
    assert result.status == "completed", result.stderr
    assert result.metrics == {"score": 0}
    assert result.provenance["outputs_returned"] is True
    try:
        assert json.loads((workspace / "probe.json").read_text()) == {
            "rename_root": "denied",
            "rename_protected_parent": "denied",
            "create_in_root": "allowed",
            "create_in_protected_parent": "allowed",
            "touch_root": "allowed",
            "chmod_root": "allowed",
            "copytree_into_root": "allowed",
            "immutable_file": "allowed",
        }
        # An immutable workload file must not leave the private evaluation copy behind.
        assert not list(workspace.parent.glob(".autoresearch-evaluation-*"))
    finally:
        os.chflags(workspace / "locked.txt", 0)


def test_zombie_only_process_groups_do_not_fail_a_finished_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """macOS reports EPERM instead of ESRCH when only zombies remain in the group."""
    from autoresearch.runtime_support import process

    def refuse(pid: int, signum: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(process.os, "killpg", refuse)
    result = process.run_process(
        [sys.executable, "-c", "print('done')"], cwd=tmp_path, env={}, timeout=30, limit=4096
    )
    assert result.returncode == 0 and "done" in result.stdout


def test_runner_reads_process_states_with_unusual_names(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    runner = _runner_module()
    stats = {
        "/proc/12/stat": b"12 (odd) name \xff) S 1 12",
        "/proc/13/stat": b"13 (gone) Z 1 13",
        "/proc/14/stat": b"14 (worker) R 1 14",
    }
    monkeypatch.setattr(runner.os, "listdir", lambda path: ["1", "12", "13", "14", "self"])
    monkeypatch.setattr(
        runner, "open", lambda path, mode="r": io.BytesIO(stats[path]), raising=False
    )
    monkeypatch.setattr(runner.os, "getpid", lambda: 2)
    assert runner._remaining_processes() == [12, 14]

    def unavailable(path: str) -> list[str]:
        raise OSError("no /proc")

    monkeypatch.setattr(runner.os, "listdir", unavailable)
    with pytest.raises(SystemExit) as stopped:
        runner._remaining_processes()
    assert stopped.value.code == 125


def test_trusted_copy_fails_closed_on_unreadable_files(tmp_path: Path) -> None:
    import time as clock

    workspace, copy = tmp_path / "work", tmp_path / "copy"
    workspace.mkdir()
    copy.mkdir()
    (workspace / "script.sh").write_text("echo")
    (workspace / "script.sh").chmod(0o755)
    (workspace / "sealed.bin").write_text("x")
    (workspace / "sealed.bin").chmod(0)
    try:
        problem = isolation.clone_workspace(
            workspace, isolation.workspace_identity(workspace), copy, clock.monotonic() + 30
        )
    finally:
        (workspace / "sealed.bin").chmod(0o600)
    if os.geteuid() != 0:
        assert "could not be copied" in problem


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["python3", "evaluate.py"], False),
        (["python3", "-m", "evaluate"], True),
        (["python3", "-u", "-m", "evaluate"], True),
        (["python3", "-X", "dev", "-c", "print(1)"], True),
        (["python3", "-mevaluate"], True),
        (["python3", "-u", "evaluate.py", "-m", "x"], False),
        (["pytest", "-c", "setup.cfg"], False),
    ],
)
def test_evaluator_import_path_warning_parses_python_options(
    argv: list[str], expected: bool
) -> None:
    from autoresearch.setup import _python_runs_module_or_code

    assert _python_runs_module_or_code(argv) is expected
