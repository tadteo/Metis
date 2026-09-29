"""Official plotting provenance must be checked, including reused installations."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from autoresearch import paper_orchestra_setup as setup
from autoresearch.paper_orchestra import PaperOrchestraError


@pytest.fixture
def installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "PaperBanana"
    root.mkdir()
    archive = root / setup.ARCHIVE_NAME
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, content in {
            "PaperBananaBench/diagram/ref.json": '[{"example": "diagram"}]',
            "PaperBananaBench/plot/ref.json": '[{"example": "plot"}]',
            "PaperBananaBench/plot/sample.png": "fixture-image",
        }.items():
            bundle.writestr(name, content)
    monkeypatch.setattr(setup, "DATA_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    setup.extract_reference_archive(archive, root / "data")
    (root / "style_guides").mkdir()
    styles = [f"style_guides/neurips2025_{task}_style_guide.md" for task in ("diagram", "plot")]
    for name in styles:
        (root / name).write_text("official fixture style")
    monkeypatch.setattr(setup, "verify_plotting_checkout", lambda _: None)
    monkeypatch.setattr(setup.subprocess, "check_output", lambda *a, **kw: "\n".join(styles))
    return root


def test_verified_archive_binds_all_reused_assets_and_snapshot(
    installation: Path, tmp_path: Path
) -> None:
    import shutil

    receipt = setup.verify_plotting_assets(installation)
    assert receipt["archive_sha256"] == setup.DATA_SHA256
    assert len(receipt["files"]) == 5
    snapshot = tmp_path / "snapshot"
    shutil.copytree(installation, snapshot)
    setup.verify_asset_snapshot(snapshot, receipt["files"])
    (snapshot / "data/PaperBananaBench/plot/sample.png").write_text("altered")
    with pytest.raises(PaperOrchestraError, match="checksum mismatch"):
        setup.verify_asset_snapshot(snapshot, receipt["files"])


@pytest.mark.parametrize("kind", ["data", "archive", "extra-style", "missing-archive", "symlink"])
def test_unverified_reused_material_cannot_claim_official_provenance(
    installation: Path, kind: str
) -> None:
    image = installation / "data/PaperBananaBench/plot/sample.png"
    if kind == "data":
        image.write_text("changed")
    elif kind == "archive":
        (installation / setup.ARCHIVE_NAME).write_bytes(b"other archive")
    elif kind == "extra-style":
        (installation / "style_guides/extra.md").write_text("untracked style")
    elif kind == "missing-archive":
        (installation / setup.ARCHIVE_NAME).unlink()
    else:
        image.unlink()
        image.symlink_to(installation / "data/PaperBananaBench/plot/ref.json")
    with pytest.raises(PaperOrchestraError):
        setup.verify_plotting_assets(installation)


def test_modified_tracked_plotting_source_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outputs = iter([setup.PAPERVIZ_REVISION, " M style_guides/neurips2025_plot_style_guide.md"])
    monkeypatch.setattr(setup.subprocess, "check_output", lambda *a, **kw: next(outputs))
    with pytest.raises(PaperOrchestraError, match="clean checkout"):
        setup.verify_plotting_checkout(tmp_path)


def test_configured_root_alias_is_resolved_but_descendant_symlinks_fail(
    installation: Path, tmp_path: Path
) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(installation, target_is_directory=True)
    receipt = setup.verify_plotting_assets(alias)
    setup.verify_asset_snapshot(alias, receipt["files"])
    real = installation / "data/PaperBananaBench/plot"
    moved = installation / "moved-plot"
    real.rename(moved)
    real.symlink_to(moved, target_is_directory=True)
    with pytest.raises(PaperOrchestraError):
        setup.verify_asset_snapshot(alias, receipt["files"])
