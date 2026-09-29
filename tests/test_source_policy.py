from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.engine import Engine
from autoresearch.setup import preflight
from autoresearch.source_policy import source_is_excluded

PRIVATE_FILES = [
    "signing.pem",
    "nested/client.key",
    "certificate.p12",
    "certificate.pfx",
    ".netrc",
    ".config/tool/account.json",
    ".codex/auth.json",
    ".agents/private-note.md",
    ".secrets/service.json",
    ".credentials/provider.json",
    ".ssh/id_rsa",
    ".aws/credentials",
    ".azure/accessTokens.json",
    ".gnupg/private-keys-v1.d/key",
    ".kube/config",
    ".docker/config.json",
    ".git-credentials",
    ".pypirc",
    ".npmrc",
    ".yarnrc.yml",
    ".env.local",
    "credentials.json",
    "Secrets.toml",
    "id_ed25519",
    "service-account.json",
    "runtime/history.json",
    "private/notes.md",
    "data/records.json",
]


@pytest.mark.parametrize("relative", PRIVATE_FILES)
def test_private_source_paths_are_excluded(relative: str) -> None:
    assert source_is_excluded(relative)


def test_wildcard_snapshot_and_preflight_share_exclusions(tmp_path: Path) -> None:
    source, target = tmp_path / "project", tmp_path / "snapshot"
    source.mkdir()
    target.mkdir()
    public = {"train.py", "evaluate.py", "README.md", "nested/requirements.txt"}
    for name in [*PRIVATE_FILES, *public]:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture data\n")

    Engine._copy_source(source, target, ["*", "**/*"])
    archived = {str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()}
    assert archived == public

    config = ResearchConfig.model_validate(
        {
            "provider": {"base_url": "http://127.0.0.1:8000/v1"},
            "execution": {"backend": "local", "allow_local": True},
            "project": {
                "source_dir": str(source),
                "include": ["*", "**/*"],
                "baseline_argv": ["python3", "train.py"],
                "evaluator_argv": ["python3", "evaluate.py"],
                "protected_paths": ["evaluate.py"],
                "sota": {"score": 0.5},
            },
        }
    )
    source_check = next(check for check in preflight(config)["checks"] if check["name"] == "source")
    assert source_check == {
        "name": "source",
        "status": "ok",
        "message": "4 source files match the snapshot include patterns.",
    }


def test_explicit_include_cannot_reenable_credentials(tmp_path: Path) -> None:
    source, target = tmp_path / "project", tmp_path / "snapshot"
    source.mkdir()
    target.mkdir()
    (source / "signing.key").write_text("fixture data")
    Engine._copy_source(source, target, ["signing.key"])
    assert not list(target.iterdir())
