"""Evidence instructions are independently inspectable writer input artifacts."""

import hashlib
import json
import shutil
from pathlib import Path

from autoresearch.catalog import ROOT, load_catalog
from autoresearch.contracts import ExperimentResult, Idea, RunState
from autoresearch.paper_orchestra import materialize_raw_materials


def test_custom_writer_evidence_prompt_is_materialized_with_provenance(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    shutil.copytree(ROOT, specs)
    prompt = specs / "prompts/writer_evidence.md"
    prompt.write_text(
        "# Synthetic evidence guidance\n\nEvery failed experiment remains evidence.\n"
    )
    catalog = load_catalog(specs)
    state = RunState(
        id="abcdefabcdef",
        title="Study",
        objective="Check inputs",
        selected_idea="idea",
        ideas=[Idea(id="idea", title="Idea", hypothesis="Mechanism")],
        experiments=[ExperimentResult(id="failure", status="failed", exit_code=1)],
    )
    target = tmp_path / "materials"
    materialize_raw_materials(state, target, catalog=catalog)
    text = (target / "experimental_log.md").read_text()
    assert text.startswith(prompt.read_text().strip())
    assert '"status": "failed"' in text and '"id": "failure"' in text
    provenance = json.loads((target / "instruction-provenance.json").read_text())
    assert provenance["catalog_sha256"] == catalog.digest
    assert (
        provenance["material_prompts"]["prompts/writer_evidence.md"]
        == hashlib.sha256(prompt.read_bytes()).hexdigest()
    )
    assert catalog.definition("draft").prompt_scope == "upstream_native"
