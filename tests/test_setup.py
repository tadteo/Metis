"""Readiness stops incomplete UI setups before paid research can begin."""

from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.privacy import redact
from autoresearch.setup import preflight


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
