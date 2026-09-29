"""Behavioral gates against replacing scientific subsystems with cheap single calls."""

import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, RunState, Stage
from autoresearch.paper_orchestra import PaperOrchestraError
from autoresearch.store import Store


def runner(tmp_path):
    config = ResearchConfig(mode="live", search_enabled=False)
    store = Store(tmp_path / "state")
    state = RunState(id="abcdef123456", title="Architecture fixture", objective="Verify routing")
    store.create(state, config)
    return AgentRunner(store, config), state


@pytest.mark.parametrize(
    "role",
    [
        "baseline",
        "subset",
        "subset_engineer",
        "full",
        "full_engineer",
        "ablation",
        "ablation_refine",
        "rebuttal",
        "meta_refine",
    ],
)
def test_every_live_implementation_stage_uses_iterative_coding(tmp_path, monkeypatch, role):
    agents, state = runner(tmp_path)
    seen = []

    def coding(actual_state, call, store, config, context):
        seen.append((actual_state.id, context["original_role"], context["source_dir"]))
        return AgentOutput(summary="Completed iterative coding fixture")

    monkeypatch.setattr("autoresearch.agents.run_coding", coding)
    monkeypatch.setattr(agents, "_one", lambda *a, **k: pytest.fail("one-shot coding bypass"))
    output = agents.run(state, role, {"source_dir": "operator-owned-source"})
    assert seen == [(state.id, role, "operator-owned-source")]
    assert output.summary == "Completed iterative coding fixture"


@pytest.mark.parametrize("role", ["draft", "revise"])
def test_live_manuscripts_use_official_writer_and_propagate_failures(tmp_path, monkeypatch, role):
    agents, state = runner(tmp_path)
    seen = []

    def official(actual_state, store, config):
        seen.append(actual_state.id)
        return "Official upstream manuscript fixture"

    monkeypatch.setattr("autoresearch.writing.run_official_writer", official)
    monkeypatch.setattr(agents, "_one", lambda *a, **k: pytest.fail("local writer fallback"))
    assert agents.run(state, role).manuscript == "Official upstream manuscript fixture"
    assert seen == [state.id]

    def failure(*args):
        raise PaperOrchestraError("upstream failed")

    monkeypatch.setattr("autoresearch.writing.run_official_writer", failure)
    with pytest.raises(PaperOrchestraError, match="upstream failed"):
        agents.run(state, role)


@pytest.mark.parametrize("coverage", [False, True])
def test_live_review_runs_scholarpeer_before_independent_panel(tmp_path, monkeypatch, coverage):
    agents, state = runner(tmp_path)
    state.stage = Stage.PEER_REVIEW
    order = []
    context = {
        "review_evidence": [],
        "individual_outputs": [{"role": "review_summary", "summary": "Structured evidence"}],
        "publication_cutoff": "2026-01-01",
        "literature_coverage": {"sufficient_for_assessment": coverage},
    }

    def review(*args):
        order.append("scholarpeer")
        return context

    def panel(actual_state, role, supplied, index, **kwargs):
        assert order[0] == "scholarpeer"
        assert supplied["individual_outputs"] == context["individual_outputs"]
        assert supplied["publication_cutoff"] == "2026-01-01"
        order.append(index)
        return AgentOutput(
            summary="Independent scored review", decision="accept", score=9, confidence=1
        )

    monkeypatch.setattr("autoresearch.agents.review_context", review)
    monkeypatch.setattr(agents, "_one", panel)
    output = agents.run(state, "peer_review")
    assert sorted(order[1:]) == [0, 1]
    assert output.decision == ("accept" if coverage else "refine")
    assert len(output.structured["panel_outputs"]) == 2
    assert any(item["kind"] == "review_context" for item in state.memory)
    artifacts = agents.store.artifacts(state.id)
    assert any(
        item["kind"] == "scholarpeer_context"
        and (agents.store.run_dir(state.id) / item["path"]).is_file()
        for item in artifacts
    )


def test_independent_critic_objection_cannot_disappear_in_consensus(tmp_path, monkeypatch):
    agents, state = runner(tmp_path)
    seen = []

    def panel(actual_state, role, context, index, **kwargs):
        seen.append(index)
        return AgentOutput(
            summary=f"Critic {index}", decision="accept" if index == 0 else "reject", confidence=1
        )

    monkeypatch.setattr(agents, "_one", panel)
    output = agents.run(state, "full_critic")
    assert sorted(seen) == [0, 1]
    assert output.decision == "reject"
    assert output.stage_decision == "bad"
    assert len(output.structured["panel_outputs"]) == 2
