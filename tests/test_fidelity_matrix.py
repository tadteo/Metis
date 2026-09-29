import json
from pathlib import Path

from autoresearch.fidelity import load_matrix, validate_matrix


def test_matrix_covers_stages_and_resolves_tests() -> None:
    root = Path(__file__).resolve().parents[1]
    matrix = load_matrix()
    validate_matrix(matrix, root)
    assert json.loads((root / "docs/fidelity.json").read_text()) == matrix
    assert matrix["scientific_parity"] is False
