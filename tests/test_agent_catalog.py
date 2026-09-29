"""Inert AI artifacts and deterministic output/routing contracts."""

from __future__ import annotations

import json
import shutil

import pytest

from autoresearch.catalog import ROOT, load_catalog
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, ProviderConfig, Stage
from autoresearch.routing import resolve_route


def copied_catalog(tmp_path):
    target = tmp_path / "specs"
    shutil.copytree(ROOT, target)
    return target


def edit_agent(root, role, **changes):
    path = root / "agents.json"
    document = json.loads(path.read_text())
    document["agents"][role].update(changes)
    path.write_text(json.dumps(document))


def test_catalog_covers_all_scientific_roles_and_prompts():
    catalog = load_catalog()
    assert set(Stage) - {Stage.COMPLETE} <= catalog.agents.keys()
    for role, agent in catalog.agents.items():
        assert agent.inputs and agent.output_schema and agent.purpose
        prompt = catalog.render(role)
        assert "untrusted data" in prompt
        assert '"$defs"' in prompt
        assert catalog.prompt(role).strip()
    assert catalog.definition("draft").prompt_scope == "upstream_native"
    assert catalog.definition("draft").upstream["revision"]
    assert "published/scholarpeer/peer_review.txt" in catalog.manifest()["artifacts"]


def test_common_guardrails_and_repair_are_versioned_and_hashed(tmp_path):
    root = copied_catalog(tmp_path)
    before = load_catalog(root)
    assert {
        "prompts/common.md",
        "prompts/repair.md",
        "policies/models.json",
        "tools/tools.json",
    } <= before.manifest()["artifacts"].keys()
    path = root / "prompts/common.md"
    path.write_text(path.read_text() + "Preserve alternative hypotheses.\n")
    after = load_catalog(root)
    assert after.digest != before.digest
    assert before.render("limitations") != after.render("limitations")
    # A loaded catalog remains a coherent snapshot while a fresh load detects drift.
    assert before.digest == before.manifest()["sha256"]


@pytest.mark.parametrize("prompt", ["../secret.md", "/outside/secret.md", "prompts/missing.md"])
def test_bad_prompt_references_fail_closed(tmp_path, prompt):
    root = copied_catalog(tmp_path)
    edit_agent(root, "limitations", prompts=[prompt])
    with pytest.raises((ValueError, FileNotFoundError)):
        load_catalog(root)


def test_symlink_prompts_and_unimplemented_tools_are_rejected(tmp_path):
    root = copied_catalog(tmp_path)
    path = root / "prompts/limitations.md"
    path.unlink()
    path.symlink_to(ROOT / "prompts/limitations.md")
    with pytest.raises(ValueError, match="symlink"):
        load_catalog(root)
    path.unlink()
    path.write_text("Synthetic limitation extraction")
    edit_agent(root, "limitations", tools=["host.unrestricted_shell"])
    with pytest.raises(ValueError, match="unknown tool"):
        load_catalog(root)


@pytest.mark.parametrize(
    ("role", "payload"),
    [
        ("limitations", {}),
        ("generate_ideas", {}),
        ("novelty", {"novelty_scores": {"idea": 11}}),
        ("ablation_plan", {"plans": [{"description": "not an executable question"}]}),
        ("peer_review", {}),
        ("draft", {"manuscript": "Too short"}),
        ("baseline", {"argv": []}),
        ("claim_extraction", {"structured": {"claims": "narrative"}}),
        ("coding_step", {"plans": [{"tool": "shell", "command": "unsafe"}]}),
        ("inspection_step", {"plans": [{"tool": "edit", "path": "model.py"}]}),
    ],
)
def test_role_contract_rejects_incomplete_accepted_output(role, payload):
    with pytest.raises(ValueError, match="contract"):
        load_catalog().validate_output(role, AgentOutput(summary="Synthetic result", **payload))


@pytest.mark.parametrize("decision", ["reject", "refine"])
def test_unresolved_producer_does_not_have_to_fabricate_success_payload(decision):
    output = AgentOutput(summary="Evidence is insufficient", decision=decision)
    assert load_catalog().validate_output("generate_ideas", output) is output


def test_routing_is_explicit_and_inherits_scientific_role():
    config = ResearchConfig(
        cheap_provider=ProviderConfig(model="cheap"),
        frontier_provider=ProviderConfig(model="frontier"),
        heldout_provider=ProviderConfig(model="heldout"),
        role_providers={
            "novelty": ProviderConfig(model="novelty-explicit"),
            "full": ProviderConfig(model="scientific-role"),
        },
        role_panels={
            "full": [ProviderConfig(model="panel-first"), ProviderConfig(model="panel-second")]
        },
    )
    assert resolve_route(config, "novelty").provider.model == "novelty-explicit"
    assert resolve_route(config, "filter_ideas").reason == "cheap"
    assert (
        resolve_route(config, "coding_step", index=1, original_role="full").provider.model
        == "panel-second"
    )
    assert (
        resolve_route(config, "coding_step", original_role="full", frontier=True).reason
        == "frontier"
    )
    assert resolve_route(config, "heldout_review").provider.model == "heldout"
    assert resolve_route(config, "limitations").reason == "default"


def test_restricted_custom_coding_tools_are_enforced(tmp_path):
    root = copied_catalog(tmp_path)
    edit_agent(root, "full", tools=["repository.list", "repository.read", "session.finish"])
    catalog = load_catalog(root)
    output = AgentOutput(
        summary="Proposed write",
        plans=[{"tool": "edit", "edits": [{"path": "model.py", "content": "new"}]}],
    )
    with pytest.raises(ValueError, match="tool_action"):
        catalog.validate_output("coding_step", output, {"original_role": "full"})


def test_experiment_plan_requires_intervention_and_expected_evidence():
    catalog = load_catalog()
    output = AgentOutput(
        summary="Synthetic experimental plan",
        plans=[{"id": "control", "question": "Does the mechanism explain the gain?"}],
    )
    with pytest.raises(ValueError, match="experiment_plans"):
        catalog.validate_output("ablation_plan", output)
    output.plans[0].update(
        intervention="Remove the component under the fixed protocol",
        expected_evidence="Seed-level changes in the registered metric",
        metric_requirements=["accuracy"],
    )
    assert catalog.validate_output("ablation_plan", output) is output
    required = catalog.output_schema("ablation_plan")["properties"]["plans"]["items"]["required"]
    assert "expected_evidence" in required
    # Reviewer questions retain their separate, simpler contract.
    catalog.validate_output(
        "review_novelty_questions",
        AgentOutput(
            summary="Question",
            plans=[{"question": "Which prior methods implement this mechanism?"}],
        ),
    )
