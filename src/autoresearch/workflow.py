"""Validated, inspectable ScientistTwo graph and runtime transition boundary."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from .contracts import Model, RunState, Stage


class WorkflowTransitionError(ValueError):
    """An action attempted an undeclared edge or lacked required research evidence."""


class Transition(Model):
    target: Stage
    condition: str = Field(min_length=1)
    guards: list[str] = Field(default_factory=list)


class WorkflowNode(Model):
    label: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    handler: str = Field(min_length=1)
    agents: list[str]
    inputs: list[str]
    outputs: list[str]
    limits: list[str]
    transitions: list[Transition]
    wait_states: list[str] = Field(default_factory=list)
    stop_outcomes: list[str] = Field(default_factory=list)
    instructions: dict[str, str] = Field(default_factory=dict)


GUARDS = {
    "limitations_present",
    "candidate_queue",
    "baseline_measured",
    "subset_accepted",
    "successful_candidates",
    "selected_candidate",
    "supplementary_plan",
    "manuscript_present",
    "refinement_recorded",
    "ablation_attributed",
    "final_evidence",
}


def _guard(name: str, state: RunState) -> bool:
    selected = next((idea for idea in state.ideas if idea.id == state.selected_idea), None)
    current = next((idea for idea in state.ideas if idea.id == state.current_idea), None)
    if name == "limitations_present":
        return bool(state.limitations)
    if name == "candidate_queue":
        return bool(state.queue) and set(state.queue) <= {idea.id for idea in state.ideas}
    if name == "baseline_measured":
        return bool(state.baseline)
    if name == "subset_accepted":
        return current is not None and current.status == "subset_good" and bool(current.metrics)
    if name == "successful_candidates":
        return any(idea.status == "good" for idea in state.ideas)
    if name == "selected_candidate":
        return selected is not None and selected.status == "good"
    if name == "supplementary_plan":
        return bool(state.plans) and all(
            isinstance(plan.get("question"), str) for plan in state.plans
        )
    if name == "manuscript_present":
        return len(state.manuscript.strip()) >= 100
    if name == "refinement_recorded":
        return state.candidate_update is not None and state.comparison_origin in {
            "meta",
            "ablation",
        }
    if name == "ablation_attributed":
        latest = next(
            (
                item
                for item in reversed(state.memory)
                if item.get("kind") == "ablation_attribution"
                and item.get("idea") == state.selected_idea
            ),
            None,
        )
        return (
            latest is not None
            and latest.get("supported") is True
            and latest.get("version") == state.version
        )
    if name == "final_evidence":
        return (
            selected is not None
            and selected.status == "good"
            and bool(selected.metrics)
            and bool(selected.workspace)
            and bool(state.manuscript)
            and state.counters.get("reproduced_final", 0) > 0
            and state.pending_experiment is None
        )
    raise WorkflowTransitionError(f"unknown workflow evidence guard: {name}")


class InterventionPolicy(Model):
    mode: Literal["explicit_operator_bypass"]
    record: Literal["human_intervention"]
    requires_idle_checkpoint: Literal[True]
    forbidden_targets: list[Stage]
    heldout_evaluated_run: str
    full_success_required: list[Stage]
    candidate_required: list[Stage]


class WorkflowDefinition(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: str
    initial: Stage
    nodes: dict[Stage, WorkflowNode]
    interruptions: dict[str, str]
    intervention: InterventionPolicy

    @model_validator(mode="after")
    def validate_graph(self) -> WorkflowDefinition:
        if set(self.nodes) != set(Stage):
            raise ValueError("workflow must cover every research Stage exactly once")
        if self.initial != Stage.LIMITATIONS:
            raise ValueError("ScientistTwo must begin with limitation extraction")
        for stage, node in self.nodes.items():
            destinations = [edge.target for edge in node.transitions]
            if len(destinations) != len(set(destinations)):
                raise ValueError(f"duplicate workflow edge from {stage}")
            for edge in node.transitions:
                if set(edge.guards) - GUARDS:
                    raise ValueError(f"unknown evidence guard in {stage}")
                if edge.target == Stage.COMPLETE and "final_evidence" not in edge.guards:
                    raise ValueError("completion edges require the final evidence guard")
            if set(node.wait_states) - {"waiting", "paused"}:
                raise ValueError(f"unknown wait state for {stage}")
        if Stage.COMPLETE not in self.intervention.forbidden_targets:
            raise ValueError("operator intervention cannot force completion")
        reachable: set[Stage] = {self.initial}
        while True:
            expanded = reachable | {
                edge.target for stage in reachable for edge in self.nodes[stage].transitions
            }
            if expanded == reachable:
                break
            reachable = expanded
        if reachable != set(Stage):
            raise ValueError("workflow contains unreachable research stages")
        return self

    def manifest(self) -> dict[str, Any]:
        """Public JSON representation used in run provenance and every interface."""
        return self.model_dump(mode="json")

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.manifest(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def validate_handlers(self, registered: set[str]) -> None:
        unknown = {node.handler for node in self.nodes.values()} - registered
        if unknown:
            raise ValueError(f"workflow references unregistered trusted actions: {sorted(unknown)}")
        from .research_stages import ACTIONS

        for stage, node in self.nodes.items():
            if node.handler not in ACTIONS:
                raise ValueError(f"workflow action has no trusted role contract: {node.handler}")
            expected = {
                stage.value if role == "$stage" else role for role in ACTIONS[node.handler].agents
            }
            if set(node.agents) != expected or len(node.agents) != len(expected):
                raise ValueError(
                    f"{stage}: declared workflow agents do not match trusted handler dependencies; "
                    f"expected {sorted(expected)}"
                )

    def validate_intervention(self, state: RunState, target: Stage | None) -> None:
        """Operator bypasses are deliberate, recorded and never bypass final evaluation isolation."""
        if any(review.get("kind") == "heldout" for review in state.reviews):
            raise ValueError(
                "held-out evaluation freezes this run; create an independent run to continue research"
            )
        if state.pending_experiment:
            raise ValueError("wait for or cancel the pending experiment before intervention")
        if target is None:
            return
        if target in self.intervention.forbidden_targets:
            raise ValueError("completion requires integrity checks; cannot force complete")
        if target in self.intervention.full_success_required and not any(
            idea.status == "good" for idea in state.ideas
        ):
            raise ValueError("this stage requires a full-benchmark successful idea")
        if target in self.intervention.candidate_required and not (
            state.current_idea or state.selected_idea
        ):
            raise ValueError("this stage requires a candidate idea")

    def validate_transition(self, previous: Stage, state: RunState) -> None:
        """Check built-in actions and operator-supplied handlers through the same gate."""
        node = self.nodes[previous]
        if state.status in {"waiting", "paused"}:
            if state.stage != previous or state.status not in node.wait_states:
                raise WorkflowTransitionError(f"{previous}: undeclared wait transition")
            return
        if state.status in {"failed", "stopped"}:
            if state.stage != previous or state.outcome not in node.stop_outcomes:
                raise WorkflowTransitionError(
                    f"{previous}: undeclared scientific stopping outcome {state.outcome}"
                )
            return
        if state.status not in {"ready", "running", "completed"}:
            raise WorkflowTransitionError(f"{previous}: undeclared action status {state.status}")
        edge = next((edge for edge in node.transitions if edge.target == state.stage), None)
        if edge is None:
            raise WorkflowTransitionError(
                f"undeclared scientific transition: {previous} -> {state.stage}"
            )
        if state.status == "completed" and state.stage != Stage.COMPLETE:
            raise WorkflowTransitionError(
                "completion requires the integrity -> complete transition"
            )
        for name in edge.guards:
            if not _guard(name, state):
                raise WorkflowTransitionError(
                    f"{previous} -> {state.stage}: evidence guard {name} failed"
                )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate workflow JSON key: {key}")
        value[key] = item
    return value


def get_workflow() -> WorkflowDefinition:
    path = files("autoresearch").joinpath("specs/workflows/scientist_two.json")
    # Re-read content so provenance checks can detect edits within a running process.
    return WorkflowDefinition.model_validate(
        json.loads(path.read_text(), object_pairs_hook=_unique_object)
    )
