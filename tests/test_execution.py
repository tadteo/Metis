from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from autoresearch.contracts import ExecutionConfig, ExperimentSpec, FileEdit
from autoresearch.execution import ExecutionError, Executor, _Process


def spec(
    root: Path,
    code: str = "import json; open('metrics.json','w').write(json.dumps({'score':0.75}))",
    **kwargs: Any,
) -> ExperimentSpec:
    return ExperimentSpec(
        id="test-experiment",
        kind="subset",
        workspace=str(root),
        argv=["python3", "-c", code],
        **kwargs,
    )


def local(**kwargs: Any) -> Executor:
    return Executor(ExecutionConfig(backend="local", allow_local=True, **kwargs))


def test_local_requires_explicit_consent(tmp_path: Path) -> None:
    with pytest.raises(ExecutionError, match="allow_local"):
        Executor(ExecutionConfig(backend="local")).run(spec(tmp_path))


def test_executes_argv_applies_edits_and_records_hashes(tmp_path: Path) -> None:
    experiment = ExperimentSpec(
        id="edited",
        kind="baseline",
        workspace=str(tmp_path),
        argv=["python3", "src/main.py"],
        files=[
            FileEdit(
                path="src/main.py",
                content="import json\nopen('metrics.json','w').write(json.dumps({'score':2}))\n",
            )
        ],
    )
    result = local().run(experiment)
    assert result.status == "completed"
    assert result.metrics == {"score": 2}
    assert len(result.provenance["code_sha256"]) == 64
    assert len(result.provenance["environment_sha256"]) == 64
    assert (tmp_path / "src/main.py").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/outside/escape.py",
        "a/../../escape.py",
        "a\\evil.py",
        "C:/evil.py",
        ".git/config",
        ".autoresearch-execution.json",
    ],
)
def test_model_edits_cannot_escape_or_replace_control_files(tmp_path: Path, path: str) -> None:
    with pytest.raises(ExecutionError):
        local().run(spec(tmp_path, files=[FileEdit(path=path, content="anything")]))


def test_symlink_directory_edit_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = tmp_path / "work"
    workspace.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExecutionError, match="symlink"):
        local().run(spec(workspace, files=[FileEdit(path="link/escape.py", content="bad")]))
    assert not (outside / "escape.py").exists()


def test_hardlink_edit_replaces_only_workspace_file(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("private original")
    workspace = tmp_path / "work"
    workspace.mkdir()
    os.link(outside, workspace / "copy.py")
    result = local().run(spec(workspace, files=[FileEdit(path="copy.py", content="replacement")]))
    assert result.status == "completed"
    assert outside.read_text() == "private original"


@pytest.mark.parametrize(
    "argv", [["sh", "-c", "true"], ["/usr/bin/python3", "-c", "pass"], ["python3;touch", "x"]]
)
def test_only_allowlisted_bare_executable_is_accepted(tmp_path: Path, argv: list[str]) -> None:
    experiment = spec(tmp_path).model_copy(update={"argv": argv})
    with pytest.raises(ExecutionError, match="explicitly allowed"):
        local().run(experiment)


@pytest.mark.parametrize(
    "value",
    [
        '{"score":NaN}',
        '{"score":true}',
        '{"score":"1"}',
        '{"score":Infinity}',
        "[]",
        '{"score":1,"score":2}',
    ],
)
def test_invalid_metrics_are_failed_experiments(tmp_path: Path, value: str) -> None:
    result = local().run(spec(tmp_path, f"open('metrics.json','w').write({value!r})"))
    assert result.status == "failed"
    assert not result.metrics


def test_stale_metrics_are_not_accepted(tmp_path: Path) -> None:
    (tmp_path / "metrics.json").write_text('{"score":100}')
    result = local().run(spec(tmp_path, "pass"))
    assert result.status == "failed"
    assert not result.metrics


def test_metrics_symlink_cannot_read_external_file(tmp_path: Path) -> None:
    target = tmp_path / "private.json"
    target.write_text('{"score":100}')
    workspace = tmp_path / "work"
    workspace.mkdir()
    code = f"import os; os.symlink({str(target)!r}, 'metrics.json')"
    result = local().run(spec(workspace, code))
    assert result.status == "failed"
    assert not result.metrics


def test_child_does_not_inherit_provider_credentials_and_logs_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "never-inherit-this")
    code = "import os,json; print('x'*100000); open('metrics.json','w').write(json.dumps({'secret_present':int('XAI_API_KEY' in os.environ)}))"
    result = local(max_log_bytes=1024).run(spec(tmp_path, code))
    assert result.status == "completed"
    assert result.metrics == {"secret_present": 0}
    assert len(result.stdout) <= 1050
    assert "[truncated]" in result.stdout


def test_timeout_is_bounded_and_returns_failure(tmp_path: Path) -> None:
    result = local().run(spec(tmp_path, "import time; time.sleep(30)", timeout_seconds=1))
    assert result.status == "timeout"
    assert result.duration_seconds < 5


def test_docker_uses_resource_limits_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "never-inherit-this")
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)

    def run(argv: list[str], **kwargs: Any) -> _Process:
        calls.append((argv, kwargs))
        (tmp_path / "metrics.json").write_text('{"score":1}')
        return _Process("", "", 0, 0.1)

    monkeypatch.setattr("autoresearch.execution._run", run)
    result = Executor(ExecutionConfig()).run(spec(tmp_path))
    assert result.status == "completed"
    command, options = calls[0]
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--memory") + 1] == "4096m"
    assert "--read-only" in command and "--cap-drop" in command
    assert all("never-inherit-this" not in value for value in command)
    assert "XAI_API_KEY" not in options["env"]
    assert calls[-1][0][1:3] == ["rm", "--force"]


def test_slurm_is_resumable_and_never_repeats_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    queue_running = True
    monkeypatch.setattr(Executor, "_tool", lambda self, name: "/usr/bin/" + name)

    def run(argv: list[str], **kwargs: Any) -> _Process:
        calls.append(argv)
        assert "XAI_API_KEY" not in kwargs["env"]
        name = Path(argv[0]).name
        if name == "sbatch":
            return _Process("12345;cluster\n", "", 0, 0.1)
        if name == "squeue":
            return _Process("RUNNING\n" if queue_running else "", "", 0, 0.1)
        if name == "sacct":
            return _Process("12345|COMPLETED|0:0|15\n12345.batch|COMPLETED|0:0|15\n", "", 0, 0.1)
        raise AssertionError(name)

    monkeypatch.setattr("autoresearch.execution._run", run)
    experiment = spec(tmp_path)
    executor = Executor(
        ExecutionConfig(backend="slurm", slurm_account="research", slurm_partition="cpu")
    )
    pending = executor.run(experiment)
    assert pending.status == "pending" and pending.job_id == "12345;cluster"
    assert executor.run(experiment).job_id == pending.job_id
    assert len(calls) == 1
    assert executor.poll(experiment, pending.job_id).status == "pending"
    queue_running = False
    (tmp_path / "metrics.json").write_text('{"score":0.9}')
    (tmp_path / ".autoresearch-stdout.log").write_text("finished")
    resumed = Executor(executor.config).poll(experiment, pending.job_id)
    assert resumed.status == "completed"
    assert resumed.metrics == {"score": 0.9}
    assert resumed.duration_seconds == 15
    assert resumed.stdout == "finished"
    assert "--clusters" in calls[-1]
    assert "--export=NONE" in calls[0]
    assert "--account" in calls[0] and "research" in calls[0]


def test_slurm_rejects_changed_spec_and_ambiguous_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Executor, "_tool", lambda self, name: name)
    monkeypatch.setattr(
        "autoresearch.execution._run", lambda *args, **kwargs: _Process("", "offline", 1, 0.1)
    )
    executor = Executor(ExecutionConfig(backend="slurm"))
    experiment = spec(tmp_path)
    assert executor.run(experiment).status == "failed"
    with pytest.raises(ExecutionError, match="uncertain"):
        executor.run(experiment)
    with pytest.raises(ExecutionError, match="different specification"):
        executor.run(experiment.model_copy(update={"seed": 2}))


def test_slurm_validates_cluster_fields_and_job_identifiers(tmp_path: Path) -> None:
    with pytest.raises(ExecutionError, match="partition"):
        Executor(ExecutionConfig(backend="slurm", slurm_partition="cpu\n#SBATCH --exclusive"))
    executor = Executor(ExecutionConfig(backend="slurm"))
    with pytest.raises(ExecutionError, match="job identifier"):
        executor.cancel("123;$(touch /tmp/no)")


def test_slurm_runner_executes_without_shell_interpolation_and_caps_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Executor, "_tool", lambda self, name: name)
    monkeypatch.setattr(
        "autoresearch.execution._run", lambda *args, **kwargs: _Process("123", "", 0, 0.1)
    )
    executor = Executor(ExecutionConfig(backend="slurm", max_log_bytes=1024))
    code = "import json; print('x'*100000); open('metrics.json','w').write(json.dumps({'score':1}))"
    executor.run(spec(tmp_path, code))
    result = subprocess.run(
        [
            "python3",
            str(tmp_path / ".autoresearch-slurm-runner.py"),
            str(tmp_path / ".autoresearch-slurm-config.json"),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".autoresearch-stdout.log").stat().st_size == 1024
    assert json.loads((tmp_path / "metrics.json").read_text()) == {"score": 1}


def test_evaluator_uses_snapshot_and_replaces_workload_metrics(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluate.py"
    evaluator.write_text(
        "open('metrics.json','w').write('{\"score\":0.4}')\nprint('evaluation complete')"
    )
    code = "open('evaluate.py','w').write('raise RuntimeError(\"modified\")'); open('metrics.json','w').write('{\"score\":999}')"
    experiment = spec(
        tmp_path,
        code,
        metadata={
            "evaluator_argv": ["python3", "evaluate.py"],
            "protected_files": ["evaluate.py"],
        },
    )
    result = local().run(experiment)
    assert result.status == "completed"
    assert result.metrics == {"score": 0.4}
    assert "evaluation complete" in result.stdout
    assert result.provenance["evaluator_isolated"] is False
    assert len(result.provenance["protected_sha256"]["evaluate.py"]) == 64


def test_evaluator_must_produce_its_own_metrics(tmp_path: Path) -> None:
    (tmp_path / "evaluate.py").write_text("pass")
    experiment = spec(
        tmp_path,
        metadata={
            "evaluator_argv": ["python3", "evaluate.py"],
            "protected_files": ["evaluate.py"],
        },
    )
    result = local().run(experiment)
    assert result.status == "failed"
    assert not result.metrics


def test_evaluator_cannot_be_edited_or_unprotected(tmp_path: Path) -> None:
    experiment = spec(tmp_path, metadata={"evaluator_argv": ["python3", "evaluate.py"]})
    with pytest.raises(ExecutionError, match="protected relative script"):
        local().run(experiment)
    experiment.metadata["protected_files"] = ["evaluate.py"]
    experiment.files = [FileEdit(path="evaluate.py", content="forged")]
    with pytest.raises(ExecutionError, match="protected evaluator"):
        local().run(experiment)


def test_docker_evaluator_snapshot_has_separate_readonly_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "evaluate.py").write_text("pass")
    calls: list[list[str]] = []
    monkeypatch.setattr(Executor, "_tool", lambda self, name: name)

    def run(argv: list[str], **kwargs: Any) -> _Process:
        calls.append(argv)
        (tmp_path / "metrics.json").write_text('{"score":1}')
        return _Process("", "", 0, 0.1)

    monkeypatch.setattr("autoresearch.execution._run", run)
    result = Executor(ExecutionConfig()).run(
        spec(
            tmp_path,
            metadata={
                "evaluator_argv": ["python3", "evaluate.py"],
                "protected_files": ["evaluate.py"],
            },
        )
    )
    assert result.status == "completed"
    assert result.provenance["evaluator_isolated"] is True
    assert any("target=/autoresearch-protected,readonly" in arg for arg in calls[0])
    driver = json.loads((tmp_path / ".autoresearch-slurm-config.json").read_text())
    assert driver["evaluator_argv"] == ["python3", "/autoresearch-protected/evaluate.py"]


@pytest.mark.parametrize(
    "state,code,expected",
    [
        ("TIMEOUT", "0:15", "timeout"),
        ("FAILED", "124:0", "timeout"),
        ("CANCELLED by 1000", "0:15", "cancelled"),
        ("OUT_OF_MEMORY", "0:9", "failed"),
    ],
)
def test_slurm_terminal_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str, code: str, expected: str
) -> None:
    monkeypatch.setattr(Executor, "_tool", lambda self, name: name)

    def run(argv: list[str], **kwargs: Any) -> _Process:
        if argv[0] == "sbatch":
            return _Process("123", "", 0, 0.1)
        if argv[0] == "squeue":
            return _Process("", "", 0, 0.1)
        return _Process(f"123|{state}|{code}|60\n", "", 0, 0.1)

    monkeypatch.setattr("autoresearch.execution._run", run)
    executor = Executor(ExecutionConfig(backend="slurm"))
    experiment = spec(tmp_path)
    assert executor.run(experiment).job_id == "123"
    result = executor.poll(experiment, "123")
    assert result.status == expected
    assert result.duration_seconds == 60


def test_docker_explicit_datasets_are_readonly_and_provenance_is_honest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, dataset = tmp_path / "work", tmp_path / "dataset"
    workspace.mkdir()
    dataset.mkdir()
    (dataset / "measurements.txt").write_text("1 2 3")
    calls: list[list[str]] = []
    monkeypatch.setattr(Executor, "_tool", lambda self, name: name)

    def run(argv: list[str], **kwargs: Any) -> _Process:
        calls.append(argv)
        (workspace / "metrics.json").write_text('{"score":1}')
        return _Process("", "", 0, 0.1)

    monkeypatch.setattr("autoresearch.execution._run", run)
    executor = Executor(ExecutionConfig(readonly_mounts={str(dataset): "/data/measurements"}))
    result = executor.run(
        spec(workspace, metadata={"dataset_manifest": {"measurements.txt": "claimed-hash"}})
    )
    assert f"type=bind,source={dataset},target=/data/measurements,readonly" in calls[0]
    assert result.provenance["data_provenance"]["mounts_applied"] is True
    assert result.provenance["data_provenance"]["manifest_verified"] is False
    assert result.provenance["data_provenance"]["operator_manifest"] == {
        "measurements.txt": "claimed-hash"
    }


@pytest.mark.parametrize("name", [".ssh", ".aws", ".env", "credentials", "private.pem"])
def test_dataset_mount_rejects_credential_names(tmp_path: Path, name: str) -> None:
    workspace, dataset = tmp_path / "work", tmp_path / "dataset"
    workspace.mkdir()
    dataset.mkdir()
    (dataset / name).write_text("synthetic fixture")
    executor = Executor(ExecutionConfig(readonly_mounts={str(dataset): "/data/input"}))
    with pytest.raises(ExecutionError, match="credential"):
        executor.run(spec(workspace))


def test_dataset_mount_rejects_symlinks_and_overlapping_workspace(tmp_path: Path) -> None:
    workspace, dataset = tmp_path / "work", tmp_path / "dataset"
    workspace.mkdir()
    dataset.mkdir()
    (dataset / "link").symlink_to(workspace)
    executor = Executor(ExecutionConfig(readonly_mounts={str(dataset): "/data/input"}))
    with pytest.raises(ExecutionError, match="symlink"):
        executor.run(spec(workspace))
    executor = Executor(ExecutionConfig(readonly_mounts={str(tmp_path): "/data/input"}))
    with pytest.raises(ExecutionError, match="overlaps"):
        executor.run(spec(workspace))


@pytest.mark.parametrize(
    "target",
    ["/workspace", "/data", "/data/../workspace", "/data/x,readonly=false", "/data/nested/path"],
)
def test_dataset_target_cannot_override_container_mounts(tmp_path: Path, target: str) -> None:
    workspace, dataset = tmp_path / "work", tmp_path / "dataset"
    workspace.mkdir()
    dataset.mkdir()
    executor = Executor(ExecutionConfig(readonly_mounts={str(dataset): target}))
    with pytest.raises(ExecutionError, match="targets"):
        executor.run(spec(workspace))


def test_bounded_process_supports_large_private_adapter_input(tmp_path: Path) -> None:
    from autoresearch.execution import _run

    payload = b"x" * 1024 * 1024
    result = _run(
        ["python3", "-c", "import sys; print(len(sys.stdin.buffer.read()))"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"]},
        timeout=10,
        limit=1024,
        input_data=payload,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == str(len(payload))


def test_slurm_finished_job_can_disappear_from_squeue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Executor, "_tool", lambda self, name: name)

    def run(argv: list[str], **kwargs: Any) -> _Process:
        if argv[0] == "sbatch":
            return _Process("123", "", 0, 0.1)
        if argv[0] == "squeue":
            return _Process("", "Invalid job id specified", 1, 0.1)
        return _Process("123|COMPLETED|0:0|3\n", "", 0, 0.1)

    monkeypatch.setattr("autoresearch.execution._run", run)
    executor = Executor(ExecutionConfig(backend="slurm"))
    experiment = spec(tmp_path)
    executor.run(experiment)
    (tmp_path / "metrics.json").write_text('{"score":1}')
    assert executor.poll(experiment, "123").status == "completed"
