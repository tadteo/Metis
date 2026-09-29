import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from autoresearch.fidelity import load_matrix, render_report, validate_matrix

ROOT = Path(__file__).resolve().parents[1]


def test_matrix_covers_stages_commits_and_resolves_tests() -> None:
    matrix = load_matrix()
    validate_matrix(matrix, ROOT, verify_commits=True)
    assert json.loads((ROOT / "docs/fidelity.json").read_text()) == matrix
    assert matrix["scientific_parity"] is False
    assert (ROOT / "fidelity-report.md").read_text() == render_report(matrix)
    assert (ROOT / "docs/fidelity.md").read_text() == render_report(matrix, prefix="../")


@pytest.mark.parametrize(
    "field", ["commits", "implementation_files", "test_evaluation", "evidence"]
)
def test_component_cannot_drop_reviewable_evidence(field: str) -> None:
    matrix = copy.deepcopy(load_matrix())
    matrix["components"][0][field] = []
    with pytest.raises(ValidationError):
        validate_matrix(matrix)


@pytest.mark.parametrize(
    "reference",
    [
        "tests/missing.py",
        "../outside.py",
        "/etc/passwd",
        "tests/test_fidelity.py::test_invented_evidence",
    ],
)
def test_matrix_rejects_missing_or_unsafe_test_evidence(reference: str) -> None:
    matrix = copy.deepcopy(load_matrix())
    matrix["components"][0]["test_evaluation"] = [reference]
    with pytest.raises(ValueError):
        validate_matrix(matrix, ROOT)


def test_matrix_rejects_invented_commit() -> None:
    matrix = copy.deepcopy(load_matrix())
    matrix["components"][0]["commits"] = ["0" * 40]
    with pytest.raises(ValueError, match="commit is absent"):
        validate_matrix(matrix, ROOT, verify_commits=True)


@pytest.mark.parametrize(
    "change", ["stage", "duplicate", "classification", "missing_without_audit", "parity"]
)
def test_matrix_rejects_fidelity_overclaims(change: str) -> None:
    matrix = copy.deepcopy(load_matrix())
    if change == "stage":
        matrix["components"].pop(0)
    elif change == "duplicate":
        matrix["components"].append(matrix["components"][0])
    elif change == "classification":
        matrix["components"][0]["classification"] = 1
    elif change == "missing_without_audit":
        matrix["components"][0].update(
            status="missing", classification=4, gap_type="unpublished", unavailable_reason=""
        )
    else:
        matrix["scientific_parity"] = True
    with pytest.raises(ValueError):
        validate_matrix(matrix)


def test_published_review_interpretation_and_honest_evidence_limits() -> None:
    matrix = load_matrix()
    report = render_report(matrix)
    assert "initial assessment plus up to two experimental rebuttal/revision cycles" in report
    assert "seed_count=8" in report and "initial_candidates=2" in report
    assert "zero autonomous research attempts" in report
    assert "tests/test_integrity.py" not in report
    assert "pending credentials" not in report
    assert "two total rounds" not in report


def test_inherited_literature_smoke_preserves_failure_and_successful_recheck() -> None:
    evidence = json.loads((ROOT / "docs/evidence/literature-live-smoke.json").read_text())
    assert any("crossref: retrieval failed" in item for item in evidence["limitations"])
    assert evidence["crossref_regression_recheck"]["returned"] == 3
    assert evidence["crossref_regression_recheck"]["status"] == "completed"
