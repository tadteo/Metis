"""Preparation is advisory, bounded and recorded independently of research."""

import json
from pathlib import Path

import pytest

from autoresearch import onboarding
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentResponse, Usage
from autoresearch.providers import ProviderError
from autoresearch.store import Store


def project(tmp_path: Path) -> ResearchConfig:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("Train with python3 train.py. Measure using evaluate.py.")
    (root / "train.py").write_text("raise RuntimeError('must never execute')")
    (root / "evaluate.py").write_text("# protected measurement adapter")
    return ResearchConfig.model_validate({"project": {"source_dir": str(root)}})


def response() -> AgentResponse:
    return AgentResponse(
        data={
            "summary": "Setup proposal",
            "structured": {
                "summary": "Training and independent evaluation are available; reference values are unknown.",
                "suggestions": [
                    {
                        "field": "project.baseline_argv",
                        "value": ["python3", "train.py"],
                        "reason": "Documented entry point",
                        "evidence": ["README.md"],
                    }
                ],
                "questions": ["Which benchmark and fixed split should be used?"],
                "blockers": ["Reference measurement is missing"],
                "drafts": [
                    {
                        "path": "adapters/metrics.py",
                        "content": "# Review before implementation",
                        "purpose": "Proposed output adapter",
                    }
                ],
            },
        },
        model="fixture",
        provider="fixture",
        usage=Usage(cost_usd=0.01, input_tokens=100, output_tokens=80),
    )


def test_discovery_excludes_secrets_symlinks_and_outputs_without_running_code(
    tmp_path: Path,
) -> None:
    config = project(tmp_path)
    root = Path(config.project.source_dir)
    (root / ".env").write_text("secret")
    (root / "outputs").mkdir()
    (root / "outputs" / "result.json").write_text('{"private":true}')
    outside = tmp_path / "external.txt"
    outside.write_text("external-private-value")
    (root / "link.py").symlink_to(outside)
    result = onboarding.inspect_project(str(root))
    assert set(result["files"]) == {"README.md", "train.py", "evaluate.py"}
    assert "external-private-value" not in json.dumps(result)
    assert result["candidates"]["baseline"] == ["train.py"]
    assert not (root / "adapters").exists()


def test_discovery_flags_cluster_launcher_and_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = project(tmp_path)
    (Path(config.project.source_dir) / "train.sbatch").write_text("#SBATCH --gpus-per-node=1")
    monkeypatch.setattr(onboarding, "MAX_DOCUMENTS", 1)
    result = onboarding.inspect_project(config.project.source_dir)
    assert result["truncated"]
    assert any("GPU/node/task" in warning for warning in result["warnings"])


def test_preview_makes_no_call_and_apply_is_explicit_without_project_or_settings_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = project(tmp_path)
    store = Store(tmp_path / "state")
    calls = []

    def complete(self, request):
        calls.append(request)
        return response()

    monkeypatch.setattr(onboarding.CompatibleProvider, "complete", complete)
    prepared = onboarding.prepare_proposal(store, config, "Improve the fixed benchmark", 1)
    assert not calls
    assert prepared["status"] == "prepared"
    result = onboarding.generate_proposal(store, prepared["id"])
    assert result["status"] == "complete"
    assert len(calls) == 1
    assert result["usage"]["cost_usd"] == 0.01
    applied = onboarding.apply_proposal(store, result["id"], config, [0])
    assert applied.project.baseline_argv == ["python3", "train.py"]
    assert config.project.baseline_argv == []
    assert applied.provider == config.provider
    assert not applied.execution.allow_local
    assert not (Path(config.project.source_dir) / "adapters").exists()
    assert store.list_runs() == []
    assert onboarding.list_proposals(store)[0]["proposal"]["blockers"]
    with pytest.raises(ValueError, match="already submitted"):
        onboarding.generate_proposal(store, result["id"])
    assert len(calls) == 1


def test_failed_provider_usage_and_uncertain_attempt_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = project(tmp_path)
    store = Store(tmp_path / "state")

    def fail(self, request):
        raise ProviderError("Timed out", usage=Usage(cost_usd=0.2, estimated=True))

    monkeypatch.setattr(onboarding.CompatibleProvider, "complete", fail)
    prepared = onboarding.prepare_proposal(store, config, "Question", 1)
    result = onboarding.generate_proposal(store, prepared["id"])
    assert result["status"] == "failed"
    assert result["usage"]["estimated"]
    assert result["usage"]["cost_usd"] == 0.2
    assert onboarding.list_proposals(store)[0]["error"] == "Timed out"
    with pytest.raises(ValueError, match="completed"):
        onboarding.apply_proposal(store, result["id"], config, [0])
    with pytest.raises(ValueError, match="already submitted"):
        onboarding.generate_proposal(store, result["id"])


@pytest.mark.parametrize(
    "field,evidence",
    [
        ("execution.allow_local", "README.md"),
        ("provider.base_url", "README.md"),
        ("project.sota", "not-inspected.md"),
    ],
)
def test_ai_cannot_grant_permissions_or_cite_unseen_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, evidence: str
) -> None:
    config = project(tmp_path)
    store = Store(tmp_path / "state")
    result = response()
    result.data["structured"]["suggestions"][0].update(field=field, evidence=[evidence])
    monkeypatch.setattr(onboarding.CompatibleProvider, "complete", lambda self, request: result)
    prepared = onboarding.prepare_proposal(store, config, "Question", 1)
    result = onboarding.generate_proposal(store, prepared["id"])
    assert result["status"] == "failed"
    assert result["usage"]["cost_usd"] == 0.01
    assert onboarding.get_proposal(store, prepared["id"])["raw_response"]


def test_budget_rejects_before_request_and_new_folder_rejects_old_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = project(tmp_path)
    store = Store(tmp_path / "state")
    with pytest.raises(ValueError, match="reservation"):
        onboarding.prepare_proposal(store, config, "Question", 0.00001)
    monkeypatch.setattr(onboarding.CompatibleProvider, "complete", lambda self, request: response())
    prepared = onboarding.prepare_proposal(store, config, "Question", 1)
    onboarding.generate_proposal(store, prepared["id"])
    config.project.source_dir = str(tmp_path / "different")
    with pytest.raises(ValueError, match="folder changed"):
        onboarding.apply_proposal(store, prepared["id"], config, [0])


@pytest.mark.parametrize("path", ["../escape.py", "/outside/escape.py", ".env", ".ssh/config"])
def test_adapter_drafts_cannot_target_external_or_secret_paths(path: str) -> None:
    with pytest.raises(ValueError):
        onboarding.DraftFile(path=path, content="", purpose="fixture")


def test_changed_evidence_cannot_be_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = project(tmp_path)
    store = Store(tmp_path / "state")
    monkeypatch.setattr(onboarding.CompatibleProvider, "complete", lambda self, request: response())
    prepared = onboarding.prepare_proposal(store, config, "Question", 1)
    onboarding.generate_proposal(store, prepared["id"])
    (Path(config.project.source_dir) / "README.md").write_text("A different protocol")
    with pytest.raises(ValueError, match="evidence changed"):
        onboarding.apply_proposal(store, prepared["id"], config, [0])


def test_preview_matches_exact_structurally_redacted_outbound_request(tmp_path: Path) -> None:
    config = project(tmp_path)
    config.project.specification = "PRIVATE_CONFIG_SENTINEL"
    config.project.dataset_manifest = {"secret": "must-not-send"}
    store = Store(tmp_path / "state")
    prepared = onboarding.prepare_proposal(store, config, "Question", 1)
    preview = prepared["request_preview"]
    request = onboarding.get_proposal(store, prepared["id"])["request"]
    assert preview["prompt"] == json.loads(request["prompt"])
    assert preview["system"] == request["system"]
    assert preview["destination"] == config.provider.base_url
    assert "PRIVATE_CONFIG_SENTINEL" in json.dumps(preview)
    assert "must-not-send" not in json.dumps(preview)
