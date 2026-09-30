"""Readiness stops incomplete UI setups before paid research can begin."""

from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.privacy import redact
from autoresearch.setup import preflight, recover_setup


def configured(tmp_path: Path) -> ResearchConfig:
    source = tmp_path / "project"
    source.mkdir()
    (source / "train.py").write_text("print('training')\n")
    (source / "evaluate.py").write_text("print('evaluation')\n")
    return ResearchConfig.model_validate(
        {
            "provider": {"base_url": "http://127.0.0.1:9999/v1", "model": "local-test"},
            "project": {
                "source_dir": str(source),
                "baseline_argv": ["python3", "train.py"],
                "evaluator_argv": ["python3", "evaluate.py"],
                "protected_paths": ["evaluate.py"],
                "sota": {"score": 0.5},
            },
            "execution": {"backend": "local", "allow_local": True},
        }
    )


def test_valid_local_config_is_ready_without_contacting_model(tmp_path: Path) -> None:
    result = preflight(configured(tmp_path))
    assert result["ready"] is True
    assert any(
        c["name"] == "provider-access" and c["status"] == "warning" for c in result["checks"]
    )


def test_setup_guidance_asks_for_root_blockers_before_dependent_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr("autoresearch.setup.shutil.which", lambda name: "/fixture/" + name)
    monkeypatch.setattr(
        "autoresearch.setup.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b""),
    )
    result = preflight(ResearchConfig(), probe_runtime=True)
    titles = [step["title"] for step in result["guidance"]]
    assert titles[0] == "Choose a project folder"
    assert "Inspect the project" not in titles
    assert "Start Docker" in titles
    assert "Prepare a Docker image" not in titles
    assert all(step["owner"] in {"metis", "you"} for step in result["guidance"])


def test_setup_guidance_offers_read_only_inspection_for_existing_source(tmp_path: Path) -> None:
    config = configured(tmp_path)
    config.project.baseline_argv = []
    config.project.evaluator_argv = []
    config.project.protected_paths = []
    result = preflight(config)
    inspection = [step for step in result["guidance"] if step["title"] == "Inspect the project"]
    assert len(inspection) == 1
    assert inspection[0]["owner"] == "metis"
    assert set(inspection[0]["checks"]) == {
        "baseline",
        "evaluator",
        "protected-evaluator",
        "protocol",
    }


def test_setup_guidance_keeps_include_failure_visible(tmp_path: Path) -> None:
    config = configured(tmp_path)
    config.project.include = ["missing/*.py"]
    result = preflight(config)
    first = result["guidance"][0]
    assert first["title"] == "Review the source snapshot"
    assert "No project files match project.include" in first["message"]
    assert first["owner"] == "metis"
    assert first["section"] == "advanced"
    assert "Choose a project folder" not in [step["title"] for step in result["guidance"]]


def test_setup_recovers_stale_include_from_eligible_files(tmp_path: Path) -> None:
    config = configured(tmp_path)
    source = Path(config.project.source_dir)
    (source / ".env").write_text("PRIVATE=synthetic\n")
    config.project.include = ["missing/*.py"]
    recovered = recover_setup(config)
    assert recovered["readiness"]["ready"]
    assert recovered["config"]["project"]["include"] == ["evaluate.py", "train.py"]
    assert config.project.include == ["missing/*.py"]
    assert ".env" not in str(recovered)
    assert recovered["actions"] == ["Selected 2 eligible source files for the snapshot."]


def test_setup_does_not_invent_source_files(tmp_path: Path) -> None:
    config = configured(tmp_path)
    source = Path(config.project.source_dir)
    (source / "train.py").unlink()
    (source / "evaluate.py").unlink()
    config.project.include = ["missing/*.py"]
    recovered = recover_setup(config)
    assert recovered["config"]["project"]["include"] == ["missing/*.py"]
    assert not recovered["readiness"]["ready"]
    assert recovered["actions"] == []


def test_setup_repairs_include_when_excerpts_are_truncated_but_inventory_is_complete(
    tmp_path: Path,
) -> None:
    config = configured(tmp_path)
    source = Path(config.project.source_dir)
    for index in range(40):
        (source / f"module_{index}.py").write_text("# synthetic fixture\n")
    config.project.include = ["missing/*.py"]
    recovered = recover_setup(config)
    assert any("Selected 42 eligible" in action for action in recovered["actions"])
    assert recovered["readiness"]["ready"]


def test_setup_skips_unreadable_files_but_keeps_binary_project_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    config = configured(tmp_path)
    source = Path(config.project.source_dir)
    (source / "asset.bin").write_bytes(b"\x00\xff")
    (source / "unreadable.py").write_text("# synthetic\n")
    config.project.include = ["missing/*.py"]
    original_open = os.open

    def guarded_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if str(path).endswith("unreadable.py"):
            raise PermissionError("synthetic unreadable fixture")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("autoresearch.setup.os.open", guarded_open)
    recovered = recover_setup(config)
    assert recovered["config"]["project"]["include"] == ["asset.bin", "evaluate.py", "train.py"]
    assert recovered["readiness"]["ready"]


def test_setup_literal_patterns_snapshot_glob_named_files(tmp_path: Path) -> None:
    from autoresearch.engine import Engine

    config = configured(tmp_path)
    source = Path(config.project.source_dir)
    (source / "data[1].csv").write_text("synthetic,1\n")
    config.project.include = ["missing/*.py"]
    recovered = recover_setup(config)
    copied = tmp_path / "copy"
    copied.mkdir()
    Engine._copy_source(source, copied, recovered["config"]["project"]["include"])
    assert (copied / "data[1].csv").read_text() == "synthetic,1\n"


def test_setup_explains_automatic_inventory_limit(tmp_path: Path) -> None:
    config = configured(tmp_path)
    source = Path(config.project.source_dir)
    for index in range(201):
        (source / f"module_{index}.py").write_text("# synthetic\n")
    config.project.include = ["missing/*.py"]
    recovered = recover_setup(config)
    source_step = next(
        step for step in recovered["readiness"]["guidance"] if "source" in step["checks"]
    )
    assert source_step["owner"] == "you"
    assert "automatic selection is limited to 200" in source_step["message"]
    assert recovered["config"]["project"]["include"] == ["missing/*.py"]


def test_setup_fetches_missing_configured_image_then_rechecks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    config = configured(tmp_path)
    config.execution.backend = "docker"
    image_available = False
    commands: list[list[str]] = []
    monkeypatch.setattr("autoresearch.setup.shutil.which", lambda name: "/fixture/" + name)

    def docker(argv: list[str], **kwargs: object) -> SimpleNamespace:
        nonlocal image_available
        commands.append(argv)
        if argv[1] == "pull":
            image_available = True
            return SimpleNamespace(returncode=0, stdout=b"")
        return SimpleNamespace(
            returncode=0 if argv[1] == "info" or image_available else 1,
            stdout=b"available" if argv[1] == "info" or image_available else b"",
        )

    monkeypatch.setattr("autoresearch.setup.subprocess.run", docker)
    recovered = recover_setup(config)
    assert recovered["readiness"]["ready"]
    assert recovered["actions"] == ["Fetched Docker image python:3.11-slim."]
    assert [argv[1] for argv in commands].count("pull") == 1
    assert all(
        argv[1] in {"info", "image", "pull"} for argv in commands if argv[0] == "/fixture/docker"
    )


def test_setup_builds_pinned_python_dependencies_without_source_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    config = configured(tmp_path)
    config.execution.backend = "docker"
    source = Path(config.project.source_dir)
    (source / "requirements.txt").write_text("numpy==2.1.0\n")
    image_id = "sha256:" + "a" * 64
    built = False
    seen_context: set[str] = set()
    monkeypatch.setattr("autoresearch.setup.shutil.which", lambda name: "/fixture/" + name)

    def docker(argv: list[str], **kwargs: object) -> SimpleNamespace:
        nonlocal built, seen_context
        if argv[0] != "/fixture/docker":
            return SimpleNamespace(returncode=0, stdout=b"available")
        if argv[1] == "build":
            built = True
            seen_context = {item.name for item in Path(argv[-1]).iterdir()}
            return SimpleNamespace(returncode=0, stdout=b"")
        if argv[1] == "info":
            return SimpleNamespace(returncode=0, stdout=b"available")
        if argv[1:3] == ["image", "inspect"]:
            return SimpleNamespace(
                returncode=0 if built else 1,
                stdout=image_id.encode() if built else b"",
            )
        raise AssertionError(f"Unexpected Docker command: {argv}")

    monkeypatch.setattr("autoresearch.setup.subprocess.run", docker)
    recovered = recover_setup(config)
    assert recovered["readiness"]["ready"]
    assert recovered["config"]["execution"]["docker_image"] == image_id
    assert seen_context == {"Dockerfile", "requirements.txt"}
    assert recovered["actions"] == [
        "Built a Docker image with the pinned Python requirements in the project folder."
    ]


def test_setup_keeps_unsupported_dependencies_blocked_instead_of_fetching_bare_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    config = configured(tmp_path)
    config.execution.backend = "docker"
    (Path(config.project.source_dir) / "requirements.txt").write_text("-e .\n")
    commands: list[list[str]] = []
    monkeypatch.setattr("autoresearch.setup.shutil.which", lambda name: "/fixture/" + name)

    def docker(argv: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(argv)
        return SimpleNamespace(
            returncode=0 if argv[1] == "info" else 1,
            stdout=b"available" if argv[1] == "info" else b"",
        )

    monkeypatch.setattr("autoresearch.setup.subprocess.run", docker)
    recovered = recover_setup(config)
    assert not recovered["readiness"]["ready"]
    assert any("dependencies need review" in action for action in recovered["actions"])
    assert not any(
        argv[1] in {"build", "pull"} for argv in commands if argv[0] == "/fixture/docker"
    )


def test_malformed_writer_credential_reference_is_never_echoed(tmp_path: Path) -> None:
    config = configured(tmp_path)
    bad_name = "BAD_NAME-invalid-value"
    config.provider.api_key_env = bad_name
    result = preflight(config)
    assert bad_name not in str(result)
    writer = next(check for check in result["checks"] if check["name"] == "paper-orchestra")
    assert writer["message"].count("Invalid writer credential environment variable name") == 1


def test_missing_protected_script_and_baseline_typo_are_actionable(tmp_path: Path) -> None:
    config = configured(tmp_path)
    config.project.baseline_argv[1] = "typo.py"
    config.project.include = ["train.py"]
    result = preflight(config)
    assert not result["ready"]
    assert {c["name"] for c in result["checks"] if c["status"] == "error"} >= {
        "baseline",
        "evaluator",
        "protected-evaluator",
    }


def test_all_routed_credentials_checked_without_exposing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = configured(tmp_path)
    config.cheap_provider = config.provider.model_copy(
        update={"base_url": "https://example.com/v1", "api_key_env": "AUTORESEARCH_TEST_TOKEN"}
    )
    monkeypatch.delenv("AUTORESEARCH_TEST_TOKEN", raising=False)
    result = preflight(config)
    assert not result["ready"]
    assert any(
        c["name"] == "provider:cheap" and "AUTORESEARCH_TEST_TOKEN" in c["message"]
        for c in result["checks"]
    )
    secret = "test-private-value-never-rendered"  # noqa: S105 - synthetic redaction fixture
    monkeypatch.setenv("AUTORESEARCH_TEST_TOKEN", secret)
    result = preflight(config)
    assert result["ready"]
    assert secret not in str(result)


def test_local_execution_requires_opt_in_and_literature_endpoint_is_checked(tmp_path: Path) -> None:
    config = configured(tmp_path)
    config.execution.allow_local = False
    config.search_endpoint = "https://example.com/works"
    result = preflight(config)
    assert {c["name"] for c in result["checks"] if c["status"] == "error"} >= {
        "execution",
        "literature",
    }


def test_demo_needs_no_project_or_credentials() -> None:
    assert preflight(ResearchConfig(mode="demo"))["ready"]


def test_authenticated_editable_config_keeps_paths_but_redacts_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRIVATE_API_KEY", "test-private-token-for-redaction")
    example_home = "/" + "Users" + "/" + "alex" + "/project"
    config = {
        "project": {"source_dir": example_home},
        "prompt": "test-private-token-for-redaction",
        "api_key_env": "PRIVATE_API_KEY",
    }
    result = redact(config, preserve_paths=True)
    assert result["project"]["source_dir"] == example_home
    assert result["prompt"] == "[REDACTED]"
    assert result["api_key_env"] == "PRIVATE_API_KEY"
    assert redact(config)["project"]["source_dir"] == "[HOME]/project"


def test_dataset_checks_fail_before_run_for_missing_mount(tmp_path: Path) -> None:
    config = configured(tmp_path)
    config.execution.readonly_mounts = {str(tmp_path / "missing"): "/data/train"}
    result = preflight(config, probe_runtime=True)
    assert not result["ready"]
    assert any("mount" in c["message"] and c["status"] == "error" for c in result["checks"])


def test_zero_exit_without_docker_server_response_is_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    config = configured(tmp_path)
    config.execution.backend = "docker"
    monkeypatch.setattr("autoresearch.setup.shutil.which", lambda name: "/fixture/" + name)
    monkeypatch.setattr(
        "autoresearch.paper_orchestra.preflight_writer",
        lambda config: {
            "ready": True,
            "errors": [],
            "unpriced_native_models": [],
        },
    )

    def probe(argv, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=b"\n" if "info" in argv else b"sha256:fixture\n",
            stderr=b"Cannot connect to Docker daemon",
        )

    monkeypatch.setattr("autoresearch.setup.subprocess.run", probe)
    result = preflight(config, probe_runtime=True)
    assert not result["ready"]
    assert any(
        check["name"] == "docker-daemon" and check["status"] == "error"
        for check in result["checks"]
    )


@pytest.mark.parametrize(
    "url,key,expected",
    [
        ("http://remote.example.org", "", "unavailable"),
        ("http://127.0.0.1:8000", "invalid key", "unavailable"),
        ("http://127.0.0.1:8000", "", "untested"),
    ],
)
def test_optional_laya_readiness_is_local_and_preserves_reasoning_fallback(
    tmp_path, monkeypatch, url, key, expected
):
    import httpx

    config = configured(tmp_path)
    config.laya.enabled = True
    config.laya.base_url = url
    config.laya.api_key_env = "LAYA_TEST_TOKEN"
    monkeypatch.setenv("LAYA_TEST_TOKEN", key)
    monkeypatch.setattr(
        httpx.Client, "post", lambda *a, **kw: pytest.fail("preflight must not infer")
    )
    result = preflight(config)
    assert result["ready"]
    check = next(c for c in result["checks"] if c["name"] == "laya")
    assert check["status"] == "warning" and expected in check["message"]
    if key:
        assert key not in str(result)


def test_writer_prerequisites_are_visible_without_claiming_service_access(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "autoresearch.paper_orchestra.preflight_writer",
        lambda config: {
            "ready": False,
            "errors": ["Missing GEMINI_API_KEY"],
            "unpriced_native_models": ["native-fixture"],
        },
    )
    result = preflight(configured(tmp_path))
    check = next(c for c in result["checks"] if c["name"] == "paper-orchestra")
    assert check["status"] == "warning" and "Manuscript stages are blocked" in check["message"]
    assert any(c["name"] == "writer-pricing" and c["status"] == "warning" for c in result["checks"])


def test_nested_scheduler_submission_is_not_an_experiment_completion(tmp_path: Path) -> None:
    config = configured(tmp_path)
    (Path(config.project.source_dir) / "submit.sh").write_text("#!/bin/sh\nsbatch train.sbatch\n")
    config.project.baseline_argv = ["bash", "submit.sh"]
    config.execution.allowed_executables.append("bash")
    readiness = preflight(config)
    assert not readiness["ready"]
    assert any(
        c["name"] == "execution-launcher" and c["status"] == "error" for c in readiness["checks"]
    )
