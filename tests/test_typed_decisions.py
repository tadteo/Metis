"""A replaceable typed agent keeps declared criteria at both schema and runtime boundaries."""

import json
import shutil

import pytest

from autoresearch.catalog import load_catalog
from autoresearch.typed_decisions import validate_answers


def test_custom_catalog_exposes_choice_and_score_contracts(tmp_path):
    original = load_catalog()
    from pathlib import Path

    import autoresearch.catalog as catalog_module

    source = Path(catalog_module.__file__).parent / "specs"
    target = tmp_path / "specs"
    shutil.copytree(source, target)
    path = target / "agents.json"
    value = json.loads(path.read_text())
    role = value["agents"]["laya_triage"]
    role["typed_questions"] = {
        "next_action": {
            "type": "choice",
            "prompt": "prompts/laya_triage.md",
            "criteria": {"inspect": "Inspect evidence", "defer": "Defer"},
        },
        "strength": {
            "type": "score",
            "prompt": "prompts/laya_triage.md",
            "criteria": ["weak", "moderate", "strong"],
        },
    }
    path.write_text(json.dumps(value))
    catalog = load_catalog(target)
    assert catalog.digest != original.digest
    output = {"answers": {"next_action": {"choice": "inspect"}, "strength": {"score": 1.75}}}
    catalog.validate_typed_output("laya_triage", output)
    properties = catalog.output_schema("laya_triage")["properties"]["answers"]["properties"]
    assert properties["next_action"]["properties"]["choice"]["enum"] == ["inspect", "defer"]
    assert properties["strength"]["properties"]["score"]["maximum"] == 2
    for answer in ({"choice": "invented"}, {"score": 1.0}):
        output["answers"]["next_action"] = answer
        with pytest.raises(ValueError):
            catalog.validate_typed_output("laya_triage", output)


@pytest.mark.parametrize("answer", [{"score": 2.1}, {"score": True}, {"score": "1"}, {"noul": 0.9}])
def test_ordered_scores_enforce_type_and_registered_scale(answer):
    with pytest.raises(ValueError):
        validate_answers(
            {"strength": {"type": "score", "criteria": ["low", "medium", "high"]}},
            {"answers": {"strength": answer}},
        )


@pytest.mark.parametrize("kind", [None, [], {}, 1, "unknown"])
def test_malformed_question_kinds_fail_before_transport(kind):
    from autoresearch.typed_decisions import validate_questions

    with pytest.raises(ValueError, match="Unsupported typed question"):
        validate_questions({"invalid": {"type": kind}})
