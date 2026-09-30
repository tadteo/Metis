"""Public synthetic contracts exercise inspectable behavior, not model quality."""

from __future__ import annotations

import hashlib
import json

import pytest
from test_agent_catalog import copied_catalog

from autoresearch.agents import AgentRunner
from autoresearch.catalog import load_catalog
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, AgentResponse, ProviderConfig, RunState
from autoresearch.prompts import system_prompt
from autoresearch.store import Store


def test_unknown_agent_fails_before_provider_call(tmp_path):
    runner, state, provider = invocation(tmp_path)
    with pytest.raises(ValueError, match="unknown agent"):
        runner.run(state, "invented_role")
    assert not provider.requests
    with pytest.raises(ValueError, match="unknown agent"):
        system_prompt("invented_role", "an override cannot create an undeclared role")


class RepairProvider:
    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request.model_copy(deep=True))
        data = (
            {
                "summary": "Synthetic limitation extraction",
                "limitations": ["Small sample uncertainty"],
            }
            if len(self.requests) > 1
            else {"summary": "Missing payload"}
        )
        return AgentResponse(data=data, model="fixture", provider="fixture")


def invocation(tmp_path, catalog=None):
    config = ResearchConfig()
    store = Store(tmp_path / "private")
    state = RunState(
        id="0123456789ab",
        title="Synthetic catalog fixture",
        objective="Verify invocation contracts",
    )
    store.create(state, config)
    provider = RepairProvider()
    return AgentRunner(store, config, provider, catalog=catalog), state, provider


def test_invalid_output_is_repaired_before_cache_and_actual_requests_are_hashed(tmp_path):
    runner, state, provider = invocation(tmp_path)
    result = runner.run(state, "limitations")
    assert result.limitations
    assert len(provider.requests) == 2
    events = [e["payload"] for e in runner.store.events(state.id) if e["kind"] == "agent_started"]
    assert events[0]["request_sha256"] != events[1]["request_sha256"]
    assert (
        events[0]["prompt_sha256"]
        == hashlib.sha256(provider.requests[0].system.encode()).hexdigest()
    )
    assert events[0]["prompt_sha256"] != events[0]["cache_key"]
    assert events[0]["catalog_sha256"] == runner.catalog.digest
    assert "limitations contract" in json.loads(provider.requests[1].prompt)["validation_issue"]
    runner.run(state, "limitations")
    assert len(provider.requests) == 2


def test_custom_agent_uses_existing_handler_without_core_edit(tmp_path):
    root = copied_catalog(tmp_path)
    path = root / "agents.json"
    document = json.loads(path.read_text())
    definition = document["agents"]["limitations"].copy()
    definition.update(role="uncertainty_auditor", purpose="Propose evidence-grounded limitations")
    document["agents"]["uncertainty_auditor"] = definition
    path.write_text(json.dumps(document))
    runner, state, _ = invocation(tmp_path, load_catalog(root))
    assert runner.run(state, "uncertainty_auditor").limitations


def test_live_coding_gets_original_role_instruction_and_operator_override(tmp_path, monkeypatch):
    config = ResearchConfig(
        prompt_overrides={
            "full": "Preserve the registered seeds and compare every full benchmark metric."
        }
    )
    store = Store(tmp_path / "private")
    state = RunState(
        id="0123456789ab", title="Synthetic coding fixture", objective="Verify prompt dispatch"
    )
    store.create(state, config)
    seen = []

    def coding(actual_state, call, actual_store, actual_config, context):
        seen.append(context)
        return AgentOutput(summary="Prepared genuine experiment", argv=["python3", "train.py"])

    monkeypatch.setattr("autoresearch.specialists.run_coding", coding)
    AgentRunner(store, config).run(state, "full", {"source_dir": "fixture"})
    assert config.prompt_overrides["full"] in seen[0]["role_instruction"]
    assert "Follow the supplied role_instruction" in seen[0]["tool_protocol"]
    assert seen[0]["catalog_digest"] == load_catalog().digest


def test_official_writer_model_slots_remain_supported(tmp_path):
    config = ResearchConfig(
        role_providers={"writing_writer": ProviderConfig(model="writer-override")}
    )
    store = Store(tmp_path / "private")
    runner = AgentRunner(store, config)
    assert runner.catalog.models.upstream_slots["writing_writer"] == "paper_orchestra"
    config.prompt_overrides["writing_writer"] = "This slot is not a local agent"
    with pytest.raises(ValueError, match="unknown agent"):
        AgentRunner(store, config)


def test_ablation_attribution_is_a_typed_accepted_output_contract():
    catalog = load_catalog()
    catalog.agents["ablation_critic"].validation = ["attribution"]
    attribution = {
        "mechanism": "A synthetic component interaction",
        "supported": True,
        "generic_controls_only": False,
        "rationale": "Matched synthetic component intervention",
        "experiment_ids": ["component"],
    }
    output = AgentOutput(
        summary="Explicit attributed evidence", structured={"attribution": attribution}
    )
    assert catalog.validate_output("ablation_critic", output) == output
    schema = catalog.output_schema("ablation_critic")
    assert "attribution" in schema["properties"]["structured"]["properties"]
    assert "required" not in schema["properties"]["structured"]
    for broken in ({}, {**attribution, "supported": "true"}, {**attribution, "experiment_ids": []}):
        with pytest.raises(ValueError, match="attribution"):
            catalog.validate_output(
                "ablation_critic",
                AgentOutput(summary="Invalid evidence", structured={"attribution": broken}),
            )
    # Honest rejection never needs fabricated positive evidence.
    catalog.validate_output(
        "ablation_critic",
        AgentOutput(summary="No supported component attribution", decision="refine"),
    )


def test_demo_attribution_is_synthetic_and_cites_only_selected_completed_ablations():
    from autoresearch.contracts import AgentRequest
    from autoresearch.demo import DemoProvider

    catalog = load_catalog()
    catalog.agents["ablation_critic"].validation = ["attribution"]
    state = {
        "counters": {"ablation_refinements": 1},
        "selected_idea": "best",
        "experiments": [
            {
                "id": "measured",
                "status": "completed",
                "provenance": {"kind": "ablation", "selected_idea": "best"},
            },
            {
                "id": "old",
                "status": "completed",
                "provenance": {"kind": "ablation", "selected_idea": "other"},
            },
            {
                "id": "failed",
                "status": "failed",
                "provenance": {"kind": "ablation", "selected_idea": "best"},
            },
        ],
    }
    request = AgentRequest(
        run_id="demo",
        stage="ablation_critic",
        role="ablation_critic",
        system="Synthetic fixture",
        prompt=json.dumps({"state": state}),
    )
    output = AgentOutput.model_validate(DemoProvider().complete(request).data)
    catalog.validate_output("ablation_critic", output)
    assert output.structured["synthetic"] is True
    assert output.structured["attribution"]["experiment_ids"] == ["measured"]
