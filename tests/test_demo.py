"""The scripted provider obeys the same scientific output shape as live agents."""

import json

import pytest

from autoresearch.contracts import AgentOutput, AgentRequest, Idea, RunState, Stage
from autoresearch.demo import DemoProvider


@pytest.mark.parametrize("stage", [Stage.ABLATION_REFINE, Stage.META_REFINE])
def test_refinement_proposes_a_hypothesis_without_inventing_measurements(stage: Stage) -> None:
    state = RunState(
        id="fixture",
        title="Synthetic refinement",
        objective="Exercise measured incumbent comparison",
        stage=stage,
        selected_idea="incumbent",
        current_idea="incumbent",
        ideas=[
            Idea(
                id="incumbent",
                title="Quadratic regression",
                hypothesis="Quadratic features improve held-out prediction.",
                status="good",
                metrics={"score": 0.9},
                workspace="previous-measurement",
            )
        ],
    )
    response = DemoProvider().complete(
        AgentRequest(
            run_id=state.id,
            stage=stage.value,
            role=stage.value,
            system="Synthetic fixture",
            prompt=json.dumps({"state": state.model_dump(mode="json")}),
        )
    )
    output = AgentOutput.model_validate(response.data)
    assert output.decision == "accept"
    assert len(output.ideas) == 1
    assert output.ideas[0].parents == ["incumbent"]
    assert output.ideas[0].hypothesis
    assert not output.ideas[0].metrics
    assert not output.ideas[0].workspace
    assert output.argv[-2:] == ["--split", "full"]
    assert state.ideas[0].metrics == {"score": 0.9}


@pytest.mark.parametrize("stage", [Stage.ABLATION_PLAN, Stage.REBUTTAL_PLAN])
def test_experiment_plans_declare_intervention_and_expected_synthetic_evidence(
    stage: Stage,
) -> None:
    state = RunState(
        id="fixture", title="Synthetic plan", objective="Measure evidence", stage=stage
    )
    response = DemoProvider().complete(
        AgentRequest(
            run_id=state.id,
            stage=stage.value,
            role=stage.value,
            system="Synthetic fixture",
            prompt=json.dumps({"state": state.model_dump(mode="json")}),
        )
    )
    output = AgentOutput.model_validate(response.data)
    assert len(output.plans) == 1
    plan = output.plans[0]
    assert all(plan[field] for field in ("id", "question", "intervention", "expected_evidence"))
    assert plan["expected_evidence"].startswith("Synthetic ")
    assert "mean squared error" in plan["expected_evidence"]
