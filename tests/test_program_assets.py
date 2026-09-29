"""Regression checks for independently inspectable standalone program assets."""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from autoresearch.runtime_support import program_source, run_process, write_file
from autoresearch.runtime_support.programs import PROGRAM_NAMES


def test_packaged_programs_are_valid_source_and_paths_are_allowlisted() -> None:
    for name in PROGRAM_NAMES:
        source = program_source(name)
        assert ast.get_docstring(ast.parse(source))
        compile(source, name + ".py", "exec")
    with pytest.raises(ValueError, match="Unknown"):
        program_source("../../contracts")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("seed", "degree", "split", "expected_score", "expected_mse", "samples"),
    [
        (0, 1, "subset", 0.4466760108931605, 1.2387591355094911, 64),
        (7, 2, "full", 0.9737866121441084, 0.02691902674465218, 256),
        (0, 2, "subset", 0.9792964780788337, 0.021141219625115115, 64),
    ],
)
def test_demo_program_preserves_pre_refactor_measurements(
    tmp_path: Path,
    seed: int,
    degree: int,
    split: str,
    expected_score: float,
    expected_mse: float,
    samples: int,
) -> None:
    # Frozen from the original embedded program at 9cd457d. Synthetic control-flow
    # fixtures, never evidence of ScientistTwo capability or scientific novelty.
    write_file(tmp_path, "benchmark.py", program_source("demo_benchmark"))
    result = run_process(
        [sys.executable, "benchmark.py", "--degree", str(degree), "--split", split],
        cwd=tmp_path,
        env={"PATH": os.defpath, "AUTORESEARCH_SEED": str(seed)},
        timeout=10,
        limit=4096,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["n_train"] == output["n_test"] == samples
    assert output["degree"] == degree
    assert output["metrics"] == pytest.approx(
        {"score": expected_score, "mse": expected_mse}, rel=1e-12
    )
    assert json.loads((tmp_path / "metrics.json").read_text()) == output["metrics"]


@pytest.mark.parametrize(
    ("override", "accepted"),
    [
        ({}, True),
        ({"predictions": [True, 1]}, False),
        ({"predictions": [float("nan"), 1]}, False),
        ({"predictions": [0]}, False),
        ({"predictions": [2, 1]}, False),
        ({"seed": 4}, False),
        ({"split": "full"}, False),
    ],
)
def test_protected_scorer_rejects_invalid_predictions_and_wrong_protocol(
    tmp_path: Path, override: dict[str, Any], accepted: bool
) -> None:
    write_file(tmp_path, "evaluate.py", program_source("evaluation_scorer"))
    write_file(
        tmp_path, "protocol.json", json.dumps({"kind": "classification", "class_labels": [0, 1]})
    )
    write_file(tmp_path, "test_targets.json", "[0, 1]")
    predictions = {"predictions": [0, 1], "seed": 3, "split": "subset", **override}
    write_file(tmp_path, "predictions.json", json.dumps(predictions))
    result = run_process(
        [sys.executable, "evaluate.py"],
        cwd=tmp_path,
        env={
            "PATH": os.defpath,
            "AUTORESEARCH_SEED": "3",
            "AUTORESEARCH_EXPERIMENT_KIND": "subset",
        },
        timeout=10,
        limit=4096,
    )
    assert (result.returncode == 0) is accepted
    assert (tmp_path / "metrics.json").exists() is accepted
    if accepted:
        assert json.loads((tmp_path / "metrics.json").read_text()) == {"score": 1.0}
