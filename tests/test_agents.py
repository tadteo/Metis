"""Scientific panel contracts exercised through the real journal and request layer."""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from autoresearch.agents import AgentRunner
from autoresearch.cli import main
from autoresearch.config import ResearchConfig
from autoresearch.contracts import (
    AgentOutput,
    AgentRequest,
    AgentResponse,
    ProviderConfig,
    RunState,
)
from autoresearch.literature import Literature
from autoresearch.review import review_context
from autoresearch.store import BudgetExceeded, Store


class PanelProvider:
    def __init__(self, answer: Callable[[AgentRequest, dict[str, Any]], AgentOutput]) -> None:
        self.answer = answer
        self.requests: list[AgentRequest] = []
        self.lock = threading.Lock()

    def complete(self, request: AgentRequest) -> AgentResponse:
        with self.lock:
            self.requests.append(request.model_copy(deep=True))
        output = self.answer(request, json.loads(request.prompt))
        return AgentResponse(data=output.model_dump(), provider="fixture", model="fixture")


def setup_panel(
    tmp_path: Path, config: ResearchConfig, provider: PanelProvider
) -> tuple[Store, RunState, AgentRunner]:
    config.search_enabled = False
    store = Store(tmp_path / "private")
    state = RunState(
        id="0123456789ab",
        title="A controlled investigation",
        objective="Evaluate held-out performance",
    )
    store.create(state, config)
    return store, state, AgentRunner(store, config, provider)


def test_critics_remain_independent_and_objections_are_preserved(tmp_path: Path) -> None:
    config = ResearchConfig()
    config.pipeline.critics = 3

    def answer(request: AgentRequest, context: dict[str, Any]) -> AgentOutput:
        assert "panel" not in context
        rigorous = context["reviewer_perspective"] == "methodological rigor"
        return AgentOutput(
            summary="Independent review",
            decision="reject" if rigorous else "accept",
            feedback="Leakage detected" if rigorous else "Meets criterion",
            score=3 if rigorous else 8,
        )

    provider = PanelProvider(answer)
    _, state, runner = setup_panel(tmp_path, config, provider)
    result = runner.run(state, "full_critic")
    assert result.decision == "reject"
    assert result.score == 3
    assert "Leakage detected" in result.feedback
    assert "Meets criterion" in result.feedback
    assert (
        len({json.loads(request.prompt)["reviewer_perspective"] for request in provider.requests})
        == 3
    )


def test_uncertainty_without_frontier_cannot_be_accepted(tmp_path: Path) -> None:
    provider = PanelProvider(
        lambda request, context: AgentOutput(summary="Insufficient evidence", confidence=0.2)
    )
    _, state, runner = setup_panel(tmp_path, ResearchConfig(), provider)
    result = runner.run(state, "subset_critic")
    assert result.decision == "refine"
    assert "no frontier provider" in result.feedback


def test_selector_disagreement_is_not_hidden_by_identical_decisions(tmp_path: Path) -> None:
    provider = PanelProvider(
        lambda request, context: AgentOutput(
            summary="Selection",
            selected_id="a" if context["reviewer_perspective"] == "methodological rigor" else "b",
        )
    )
    _, state, runner = setup_panel(tmp_path, ResearchConfig(), provider)
    result = runner.run(state, "select")
    assert result.decision == "refine"


def test_frontier_receives_both_selector_opinions_and_original_context(tmp_path: Path) -> None:
    config = ResearchConfig(frontier_provider=ProviderConfig(model="frontier"))

    def answer(request: AgentRequest, context: dict[str, Any]) -> AgentOutput:
        if "panel" in context:
            assert {item["selected_id"] for item in context["panel"]} == {"a", "b"}
            assert context["protocol"] == "held-out only"
            assert context["escalation_reason"] == "disagreement"
            return AgentOutput(summary="Escalated decision", selected_id="b")
        return AgentOutput(
            summary="Independent decision",
            selected_id="a" if context["reviewer_perspective"] == "methodological rigor" else "b",
        )

    provider = PanelProvider(answer)
    _, state, runner = setup_panel(tmp_path, config, provider)
    result = runner.run(state, "select", {"protocol": "held-out only"})
    assert result.selected_id == "b"
    assert len(provider.requests) == 3


def test_generators_deduplicate_hypotheses_without_colliding_identifiers(tmp_path: Path) -> None:
    config = ResearchConfig()
    config.pipeline.agents_per_role = 2

    def answer(request: AgentRequest, context: dict[str, Any]) -> AgentOutput:
        perspective = context["reviewer_perspective"]
        return AgentOutput.model_validate(
            {
                "summary": "Distinct candidate mechanisms",
                "ideas": [
                    {"id": "candidate", "title": "Shared", "hypothesis": "Shared mechanism"},
                    {
                        "id": "candidate",
                        "title": "Distinct",
                        "hypothesis": f"Distinct mechanism for {perspective}",
                    },
                ],
            }
        )

    provider = PanelProvider(answer)
    _, state, runner = setup_panel(tmp_path, config, provider)
    result = runner.run(state, "generate_ideas")
    assert len(result.ideas) == 3
    assert len({idea.id for idea in result.ideas}) == 3
    assert len({idea.hypothesis for idea in result.ideas}) == 3


def test_generator_uncertainty_cannot_bypass_escalation_policy(tmp_path: Path) -> None:
    provider = PanelProvider(
        lambda request, context: AgentOutput(
            summary="Uncertain hypothesis",
            confidence=0.1,
            ideas=[
                {"id": "proposal", "title": "Proposal", "hypothesis": "A falsifiable mechanism"}
            ],
        )
    )
    _, state, runner = setup_panel(tmp_path, ResearchConfig(), provider)
    result = runner.run(state, "generate_ideas")
    assert result.decision != "accept"


@pytest.mark.parametrize("selected_id", ["-1", "100", "not-an-index"])
def test_artifact_selector_rejects_invalid_indices(tmp_path: Path, selected_id: str) -> None:
    config = ResearchConfig()
    config.pipeline.agents_per_role = 2
    provider = PanelProvider(
        lambda request, context: AgentOutput(
            summary="Artifact",
            manuscript="Draft",
            limitations=["The registered baseline omits uncertainty estimates."],
            selected_id=selected_id if context.get("artifact_selection") else None,
        )
    )
    _, state, runner = setup_panel(tmp_path, config, provider)
    with pytest.raises(ValueError, match="selector|selection|candidate"):
        runner.run(state, "limitations")


def test_artifact_selector_cannot_return_a_rejected_artifact(tmp_path: Path) -> None:
    config = ResearchConfig()
    config.pipeline.agents_per_role = 2

    def answer(request: AgentRequest, context: dict[str, Any]) -> AgentOutput:
        if context.get("artifact_selection"):
            return AgentOutput(
                summary="Neither draft satisfies the evidence", decision="reject", selected_id="0"
            )
        return AgentOutput(summary="Draft", limitations=["Missing held-out robustness controls"])

    provider = PanelProvider(answer)
    _, state, runner = setup_panel(tmp_path, config, provider)
    with pytest.raises(ValueError, match="selector|selection|candidate|reject"):
        runner.run(state, "limitations")


def test_cached_successful_subcall_survives_operational_resume_checkpoint(tmp_path: Path) -> None:
    provider = PanelProvider(
        lambda request, context: AgentOutput(
            summary="Measured conclusion", limitations=["Limited evidence on robustness"]
        )
    )
    store, state, runner = setup_panel(tmp_path, ResearchConfig(), provider)
    first = runner.run(state, "limitations")
    # Restart/status checkpoints change journal metadata, not the scientific input.
    store.save(state, "resumed")
    second = runner.run(state, "limitations")
    assert first == second
    assert len(provider.requests) == 1
    state.feedback = "Include an additional control experiment"
    runner.run(state, "limitations")
    assert len(provider.requests) == 2


def test_review_rejects_empty_question_plans() -> None:
    def call(role: str, context: dict[str, Any]) -> AgentOutput:
        return AgentOutput(
            summary=role,
            plans=[{"unrelated": "not a probing question"}] if role.endswith("questions") else [],
            structured={"claims": ["claim"], "method": "method", "evidence": ["result"]},
        )

    literature = Literature(ResearchConfig(search_enabled=False))
    state = RunState(
        id="0123456789ab",
        title="Controlled investigation",
        objective="Review experimental evidence",
    )
    with pytest.raises(ValueError, match="question"):
        review_context(state, call, literature, 2)


def test_explicit_role_provider_takes_priority_over_cheap_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected: list[str] = []

    class ConfiguredProvider:
        def __init__(self, config: ProviderConfig) -> None:
            selected.append(config.model)

        def complete(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                data={"summary": "Checked", "novelty_scores": {"candidate": 8}},
                model="fixture",
                provider="fixture",
            )

    monkeypatch.setattr("autoresearch.agents.CompatibleProvider", ConfiguredProvider)
    config = ResearchConfig(
        cheap_provider=ProviderConfig(model="cheap"),
        role_providers={"novelty": ProviderConfig(model="explicit")},
    )
    store = Store(tmp_path)
    state = RunState(id="0123456789ab", title="Routing", objective="Verify explicit routing")
    store.create(state, config)
    AgentRunner(store, config).run(state, "novelty")
    assert selected == ["explicit", "explicit"]


def adapter_runner(
    tmp_path: Path, script: str, cap: float = 0
) -> tuple[Store, RunState, AgentRunner]:
    config = ResearchConfig(
        role_commands={"baseline": [sys.executable, "-c", script]},
        role_command_max_cost_usd={"baseline": cap},
    )
    config.execution.max_log_bytes = 1024
    store = Store(tmp_path / "private")
    state = RunState(
        id="0123456789ab", title="Trusted adapter", objective="Verify bounded execution"
    )
    store.create(state, config)
    return store, state, AgentRunner(store, config)


def test_external_adapter_requires_an_explicit_cost_cap() -> None:
    with pytest.raises(ValueError, match="cost_usd cap"):
        ResearchConfig(role_commands={"baseline": ["adapter"]})
    with pytest.raises(ValueError):
        ResearchConfig(role_command_max_cost_usd={"baseline": float("inf")})


def test_external_adapter_gets_bounded_request_and_sanitized_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UNRELATED_API_KEY", "synthetic-unrelated-value")
    script = "import json,os,sys; r=json.load(sys.stdin); assert r['role']=='baseline'; assert 'UNRELATED_API_KEY' not in os.environ; assert os.environ['AUTORESEARCH_MAX_COST_USD']=='0.0'; print(json.dumps({'data':{'summary':os.environ['AUTORESEARCH_MODEL'],'argv':['python3','baseline.py']},'model':'adapter','provider':'fixture'}))"
    store, state, runner = adapter_runner(tmp_path, script)
    result = runner.run(state, "baseline")
    assert result.summary == runner.config.provider.model
    assert store.usage(state.id)["cost_usd"] == 0


def test_external_adapter_rejects_excessive_output_without_recording_raw_output(
    tmp_path: Path,
) -> None:
    store, state, runner = adapter_runner(tmp_path, "print('sensitive-fixture-' * 200)", cap=0.25)
    with pytest.raises(ValueError, match="output limit"):
        runner.run(state, "baseline")
    assert store.usage(state.id)["cost_usd"] == 0.25
    assert "sensitive-fixture" not in json.dumps(store.events(state.id))


def test_external_adapter_charges_reported_cost_before_rejecting_overrun(tmp_path: Path) -> None:
    script = "import json; print(json.dumps({'data':{'summary':'Done'},'model':'adapter','provider':'fixture','usage':{'cost_usd':0.5}}))"
    store, state, runner = adapter_runner(tmp_path, script, cap=0.25)
    with pytest.raises(BudgetExceeded):
        runner.run(state, "baseline")
    assert store.usage(state.id)["cost_usd"] == 0.5


def test_cli_budget_updates_only_explicit_limits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = PanelProvider(lambda request, context: AgentOutput(summary="Unused"))
    store, state, _ = setup_panel(tmp_path, ResearchConfig(), provider)
    before = store.get_config(state.id)
    assert (
        main(["--state-dir", str(store.root), "budget", state.id, "--usd", "50", "--calls", "2500"])
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["usd"] == 50
    assert output["max_calls"] == 2500
    assert output["max_experiments"] == before.budget.max_experiments
    assert store.get_config(state.id).provider == before.provider


def test_known_credentials_are_redacted_before_model_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.engine import Engine

    credential = "test_private_api_credential_value"
    monkeypatch.setenv("XAI_API_KEY", credential)
    store = Store(tmp_path / "runtime")
    state = Engine(store).create("Privacy", f"Inspect source containing {credential}", demo=True)
    captured: list[str] = []

    class Capture:
        def complete(self, request: AgentRequest) -> AgentResponse:
            captured.append(request.prompt)
            return AgentResponse(
                data={"summary": "safe", "limitations": ["bounded evidence"]},
                model="fixture",
                provider="fixture",
            )

    runner = AgentRunner(store, store.get_config(state.id), Capture())
    runner.run(state, "limitations")
    assert captured and credential not in captured[0]
    assert "[REDACTED]" in captured[0]


def test_final_heldout_request_excludes_optimization_review_history(tmp_path: Path) -> None:
    captured = []

    def answer(request: AgentRequest, context: dict[str, Any]) -> AgentOutput:
        captured.append(context)
        return AgentOutput(summary="Independent final assessment", score=7)

    _, state, runner = setup_panel(tmp_path, ResearchConfig(), PanelProvider(answer))
    state.manuscript = "Frozen final manuscript"
    state.feedback = "Optimize until the improvement reviewer gives score 10"
    state.reviews = [{"kind": "peer_review", "review": {"score": 10}}]
    state.memory = [{"kind": "critique", "private_optimization_signal": "target 10"}]
    runner.run(state, "heldout_review", {"frozen_manuscript_sha256": "frozen"})
    assert captured
    for context in captured:
        assert context["state"]["manuscript"] == state.manuscript
        assert not {"reviews", "feedback", "memory"} & context["state"].keys()
        assert context["frozen_manuscript_sha256"] == "frozen"


def test_reopened_run_cannot_feed_legacy_heldout_scores_into_optimization(tmp_path: Path) -> None:
    provider = PanelProvider(
        lambda request, context: AgentOutput(
            summary="Routine extraction", limitations=["Evidence is bounded"]
        )
    )
    _, state, runner = setup_panel(tmp_path, ResearchConfig(), provider)
    state.reviews = [
        {"kind": "peer_review", "feedback": "Improve the actual method"},
        {
            "kind": "heldout",
            "review": {"feedback": "FINAL_BENCHMARK_SECRET"},
            "optimization_feedback": False,
        },
    ]
    runner.run(state, "limitations")
    assert all("FINAL_BENCHMARK_SECRET" not in request.prompt for request in provider.requests)
    assert all("Improve the actual method" in request.prompt for request in provider.requests)
    assert len(state.reviews) == 2


def test_frontier_source_audit_preserves_operator_task_override(tmp_path, monkeypatch):
    import autoresearch.specialists as specialists_module

    config = ResearchConfig()
    config.pipeline.critics = 1
    config.frontier_provider = ProviderConfig(model="strong-reviewer")
    config.prompt_overrides["method_alignment"] = (
        "Verify the registered group-wise leakage constraint."
    )
    provider = PanelProvider(lambda request, context: AgentOutput(summary="unused"))
    _, state, runner = setup_panel(tmp_path, config, provider)
    tasks = []

    def inspection(state, role, call, store, config, context, *, catalog=None):
        tasks.append(context["task"])
        return AgentOutput(summary="Inspected", confidence=0.2 if len(tasks) == 1 else 0.95)

    monkeypatch.setattr(specialists_module, "inspect_code", inspection)
    runner.run(state, "method_alignment", {"source_dir": str(tmp_path)})
    assert len(tasks) == 2
    assert tasks[0] == tasks[1]
    assert config.prompt_overrides["method_alignment"] in tasks[1]


def test_coding_specialist_subcalls_keep_accounting_cache_and_frontier(tmp_path, monkeypatch):
    config = ResearchConfig(frontier_provider=ProviderConfig(model="frontier-fixture"))
    provider = PanelProvider(
        lambda request, ctx: AgentOutput(
            summary="Inspect source", plans=[{"tool": "read", "path": "model.py"}]
        )
    )
    store, state, runner = setup_panel(tmp_path, config, provider)
    supplied = {"source_dir": "public-fixture"}

    def coding(actual_state, call, actual_store, actual_config, context):
        assert context["original_role"] == "full"
        call("coding_step", {"original_role": "full", "escalate": True})
        return AgentOutput(summary="Prepared experiment", argv=["python3", "train.py"])

    monkeypatch.setattr("autoresearch.specialists.run_coding", coding)
    first = runner.run(state, "full", supplied)
    usage = store.usage(state.id)
    assert usage["calls"] == 1
    second = runner.run(state, "full", supplied)
    assert first == second
    assert store.usage(state.id) == usage
    assert len(provider.requests) == 1
    assert provider.requests[0].role == "coding_step"
    assert supplied == {"source_dir": "public-fixture"}
    cache = next(e for e in store.events(state.id) if e["kind"] == "agent_cache")
    assert cache["payload"]["configured_model"] == "frontier-fixture"
