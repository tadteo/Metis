"""Task templates remain separate from agent definitions and bind prompt revisions."""

import json
import shutil
from pathlib import Path

import pytest

from autoresearch.catalog import ROOT, load_catalog


def test_evaluation_task_preserves_exact_original_objective() -> None:
    catalog = load_catalog()
    assert catalog.render_task("evaluation", identifier="iris", metric="accuracy") == (
        "Evaluation battery task iris; score is accuracy. "
        "Reference full metrics are measured registered baselines, not claimed published SOTA. "
        "Train on train_data.json only, using protocol.json subset_indices during subset stages and all training rows in full stages. "
        "Never access test_targets.json during fitting or select methods by held-out labels. "
        "Never retrieve alternate dataset copies or change splits, targets, evaluator or protocol. "
        "Standardization and all learned preprocessing must be fit on training rows only. "
        "Full, ablation and rebuttal commands must use --split full. Record each mechanism and component removal. "
        "Repeated seeds provide reproducibility observations, not an automatic significance test. "
        "These public labels are not cryptographically hidden; independent code/protocol audit is required."
    )
    assert "evaluation" not in catalog.agents
    assert catalog.manifest()["tasks"]["evaluation"]["version"] == "1.0.0"
    assert "tasks/evaluation.md" in catalog.manifest()["artifacts"]
    with pytest.raises(ValueError, match="declared inputs"):
        catalog.render_task("evaluation", identifier="iris")


def test_task_template_drift_and_unknown_variables_are_detected(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    shutil.copytree(ROOT, specs)
    catalog = load_catalog(specs)
    path = specs / "tasks/evaluation.md"
    path.write_text(path.read_text() + " Preserve negative attempts.\n")
    assert load_catalog(specs).digest != catalog.digest
    document = json.loads((specs / "agents.json").read_text())
    document["tasks"]["evaluation"]["inputs"] = ["identifier"]
    (specs / "agents.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="variables"):
        load_catalog(specs)
