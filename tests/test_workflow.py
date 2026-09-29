"""The inspectable workflow governs actual runtime dispatch, edges and evidence gates."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from autoresearch.config import ResearchConfig
from autoresearch.contracts import RunState, Stage
from autoresearch.engine import Engine
from autoresearch.research_stages import HANDLERS
from autoresearch.store import Store
from autoresearch.workflow import WorkflowDefinition, WorkflowTransitionError, get_workflow


def test_workflow_covers_every_stage_and_resolves_runtime_contracts():
    workflow = get_workflow()
    assert set(workflow.nodes) == set(Stage)
    workflow.validate_handlers(set(HANDLERS))
    config = ResearchConfig()
    for node in workflow.nodes.values():
        assert node.inputs and node.outputs and node.label and node.phase
        for limit in node.limits:
            current = config
            for name in limit.split("."):
                current = getattr(current, name)
    manifest = workflow.manifest()
    assert manifest["nodes"]["meta_refine"]["transitions"][1]["target"] == "compare"
    assert (
        workflow.digest
        == hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert WorkflowDefinition.model_validate(manifest).digest == workflow.digest


@pytest.mark.parametrize(
    "damage", ["missing_stage", "unknown_guard", "unguarded_completion", "duplicate_edge"]
)
def test_invalid_workflow_definitions_fail_closed(damage):
    manifest = get_workflow().manifest()
    if damage == "missing_stage":
        del manifest["nodes"]["novelty"]
    elif damage == "unknown_guard":
        manifest["nodes"]["limitations"]["transitions"][0]["guards"] = ["trust_model"]
    elif damage == "unguarded_completion":
        manifest["nodes"]["integrity"]["transitions"][-1]["guards"] = []
    else:
        manifest["nodes"]["limitations"]["transitions"] *= 2
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate(manifest)


def test_specification_cannot_execute_an_unregistered_handler():
    manifest = get_workflow().manifest()
    manifest["nodes"]["limitations"]["handler"] = "arbitrary.module.callable"
    workflow = WorkflowDefinition.model_validate(manifest)
    with pytest.raises(ValueError, match="unregistered"):
        workflow.validate_handlers(set(HANDLERS))


@pytest.mark.parametrize("target", [Stage.DRAFT, Stage.COMPLETE])
def test_custom_handler_cannot_skip_undeclared_scientific_edges(tmp_path, target):
    store = Store(tmp_path)

    def bypass(state, config, runner):
        state.stage = target
        state.memory.append({"kind": "attempted_bypass", "target": target})

    engine = Engine(store, stage_handlers={Stage.LIMITATIONS: bypass})
    state = engine.create("Workflow guard", "Preserve scientific gates", demo=True)
    after = engine.step(state.id)
    assert after.status == "blocked"
    assert after.stage == Stage.LIMITATIONS
    assert "undeclared scientific transition" in after.error
    assert after.memory[-1]["kind"] == "attempted_bypass"
    assert store.get_run(state.id).stage == Stage.LIMITATIONS


def test_custom_handler_must_satisfy_declared_evidence_guard(tmp_path):
    store = Store(tmp_path)

    def empty_extraction(state, config, runner):
        state.stage = Stage.VERIFY_LIMITATIONS

    engine = Engine(store, stage_handlers={Stage.LIMITATIONS: empty_extraction})
    state = engine.create("Evidence guard", "Do not verify absent limitations", demo=True)
    after = engine.step(state.id)
    assert after.status == "blocked"
    assert after.stage == Stage.LIMITATIONS
    assert "limitations_present" in after.error


def test_custom_handler_can_follow_declared_contract(tmp_path):
    store = Store(tmp_path)

    def extract(state, config, runner):
        state.limitations = ["Synthetic fixture limitation"]
        state.stage = Stage.VERIFY_LIMITATIONS

    engine = Engine(store, stage_handlers={Stage.LIMITATIONS: extract})
    state = engine.create("Extension", "Use a trusted replacement extractor", demo=True)
    after = engine.step(state.id)
    assert after.status == "ready"
    assert after.stage == Stage.VERIFY_LIMITATIONS


def test_completion_requires_rerun_evidence_even_on_declared_edge():
    state = RunState(id="fixture", title="Final guard", objective="No invented acceptance")
    state.stage, state.status = Stage.COMPLETE, "completed"
    with pytest.raises(WorkflowTransitionError, match="final_evidence"):
        get_workflow().validate_transition(Stage.INTEGRITY, state)


def test_wait_and_scientific_stop_are_distinct_graph_outcomes():
    state = RunState(id="fixture", title="Outcomes", objective="Preserve uncertainty")
    state.stage, state.status = Stage.BASELINE, "waiting"
    get_workflow().validate_transition(Stage.BASELINE, state)
    state.stage = Stage.SUBSET
    with pytest.raises(WorkflowTransitionError, match="wait transition"):
        get_workflow().validate_transition(Stage.BASELINE, state)
    state.stage, state.status, state.outcome = (
        Stage.FULL_CRITIC,
        "failed",
        "no_successful_full_benchmark_idea",
    )
    get_workflow().validate_transition(Stage.FULL_CRITIC, state)
    state.outcome = "unrecorded_success"
    with pytest.raises(WorkflowTransitionError, match="stopping outcome"):
        get_workflow().validate_transition(Stage.FULL_CRITIC, state)


@pytest.mark.parametrize("target", [None, "draft", "meta_refine"])
def test_heldout_evaluation_freezes_research_before_intervention_mutates_state(tmp_path, target):
    store = Store(tmp_path)
    engine = Engine(store)
    state = engine.create("Frozen evaluation", "Keep final evaluation independent", demo=True)
    state.reviews.append(
        {"kind": "heldout", "review": {"score": 9}, "optimization_feedback": False}
    )
    state.feedback = "Earlier optimization feedback"
    store.save(state)
    before = store.get_run(state.id).model_dump()
    with pytest.raises(ValueError, match="held-out evaluation freezes"):
        engine.intervene(state.id, "Use the held-out review to revise", target)
    assert store.get_run(state.id).model_dump() == before


def test_workflow_edits_are_visible_to_provenance_in_the_same_process(tmp_path, monkeypatch):
    manifest = get_workflow().manifest()
    path = tmp_path / "specs" / "workflows" / "scientist_two.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr("autoresearch.workflow.files", lambda package: tmp_path)
    original = get_workflow().digest
    manifest["nodes"]["novelty"]["instructions"]["assessment"] += " Revised version."
    path.write_text(json.dumps(manifest))
    assert get_workflow().digest != original


def test_duplicate_workflow_keys_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "specs" / "workflows" / "scientist_two.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"id": "first", "id": "silently-overridden"}')
    monkeypatch.setattr("autoresearch.workflow.files", lambda package: tmp_path)
    with pytest.raises(ValueError, match="duplicate workflow JSON key"):
        get_workflow()


@pytest.mark.parametrize(
    "stage,agents",
    [
        ("full_critic", ["subset_critic"]),
        ("limitations", ["limitations"]),
        ("full", ["full"]),
        ("peer_review", ["peer_review"]),
        ("integrity", ["integrity", "heldout_review"]),
        ("limitations", ["limitations", "limitations"]),
    ],
)
def test_declared_roles_cannot_disagree_with_trusted_handler_dependencies(stage, agents):
    manifest = get_workflow().manifest()
    manifest["nodes"][stage]["agents"] = agents
    workflow = WorkflowDefinition.model_validate(manifest)
    with pytest.raises(ValueError, match="trusted handler dependencies"):
        workflow.validate_handlers(set(HANDLERS))


def test_engine_refuses_misleading_graph_roles_before_creating_a_run(tmp_path, monkeypatch):
    manifest = get_workflow().manifest()
    manifest["nodes"]["full_critic"]["agents"] = ["subset_critic"]
    workflow = WorkflowDefinition.model_validate(manifest)
    monkeypatch.setattr("autoresearch.engine.get_workflow", lambda: workflow)
    store = Store(tmp_path)
    with pytest.raises(ValueError, match="trusted handler dependencies"):
        Engine(store)
    assert store.list_runs() == []


def test_ablation_draft_edge_requires_current_attribution_evidence():
    from autoresearch.contracts import Idea

    workflow = get_workflow()
    state = RunState(
        id="ablation-gate",
        title="Evidence gate",
        objective="No implicit approval",
        selected_idea="best",
        stage=Stage.DRAFT,
        version=4,
    )
    state.ideas = [Idea(id="best", title="Selected", hypothesis="Mechanism", status="good")]
    with pytest.raises(WorkflowTransitionError, match="ablation_attributed"):
        workflow.validate_transition(Stage.ABLATION_CRITIC, state)
    state.memory.append(
        {"kind": "ablation_attribution", "idea": "best", "supported": True, "version": 3}
    )
    with pytest.raises(WorkflowTransitionError, match="ablation_attributed"):
        workflow.validate_transition(Stage.ABLATION_CRITIC, state)
    state.memory[-1]["version"] = 4
    workflow.validate_transition(Stage.ABLATION_CRITIC, state)
