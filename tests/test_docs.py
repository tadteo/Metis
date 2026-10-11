"""Documentation failures should be caught before a reader reaches GitHub."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts/check_docs.py")
assert spec and spec.loader
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def test_links_cover_markdown_html_images_and_duplicate_headings(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text("# Setup\n\n## Setup\n\n## **Model** `access`\n")
    (tmp_path / "image.png").write_bytes(b"public fixture")
    (tmp_path / "README.md").write_text(
        "# Home\n\n"
        "[guide][setup]\n\n[setup]: docs/guide.md#setup-1\n\n"
        "[model](docs/guide.md#model-access)\n\n![demo](image.png)\n\n"
        '<picture><source srcset="image.png"><img src="image.png"></picture>\n\n'
        "[site](https://example.org/)\n\n`[ignored](missing.md)`\n\n"
        "```bash\n# [ignored](missing.md)\n```\n"
    )
    assert docs.check_links(tmp_path) == []
    with (tmp_path / "README.md").open("a") as file:
        file.write('\n[broken](docs/guide.md#absent)\n\n<img src="absent.png">\n')
    failures = docs.check_links(tmp_path)
    assert len(failures) == 2
    assert any("absent.png: missing" in error for error in failures)
    assert any("#absent: missing heading" in error for error in failures)


def test_link_to_unindexed_markdown_and_outside_repository(tmp_path):
    (tmp_path / "docs/plans").mkdir(parents=True)
    (tmp_path / "docs/plans/task.md").write_text("# Accepted plan\n")
    (tmp_path / "README.md").write_text(
        "[plan](docs/plans/task.md#accepted-plan)\n\n[outside](../outside.md)\n"
    )
    failures = docs.check_links(tmp_path)
    assert len(failures) == 1
    assert "outside repository" in failures[0]


def test_cli_reference_detects_drift_and_ignores_terminal_width(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    monkeypatch.setenv("COLUMNS", "40")
    content = docs.cli_reference()
    assert "## metis remote add" in content
    assert "--remote-db-dir" in content
    assert "--clear-quota" in content
    (tmp_path / "docs/cli.md").write_text(content)
    monkeypatch.setenv("COLUMNS", "160")
    assert docs.check_cli(tmp_path) == []
    (tmp_path / "docs/cli.md").write_text(content.replace("--clear-quota", "--old-flag"))
    assert docs.check_cli(tmp_path)


def test_public_guides_and_generated_cli_are_current():
    assert docs.check_links(ROOT) == []
    assert docs.check_cli(ROOT) == []
