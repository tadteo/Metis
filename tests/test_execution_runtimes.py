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
    assert '(deny file-write* (literal (param "PROTECT0")))' in profile
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
    paths = isolation.python_paths(sys.executable)
    assert isolation.canonical(Path(sys.prefix)) in paths
    assert isolation.python_paths("/usr/bin/Rscript") == []


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
