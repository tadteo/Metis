"""Published stage-specific decisions with a legacy checkpoint migration boundary."""

from .contracts import AgentOutput

STAGE_DECISIONS = {
    "subset_critic": {"good": "accept", "engineer": "refine", "bad": "reject"},
    "full_critic": {"good": "accept", "engineer": "refine", "bad": "reject"},
    "ablation_critic": {"good": "accept", "refine": "refine"},
    "meta_review": {"accept": "accept", "refine": "refine"},
    "compare": {"superior": "accept", "not_superior": "reject"},
}


def normalize_decision(role: str, output: AgentOutput) -> AgentOutput:
    vocabulary = STAGE_DECISIONS.get(role)
    if vocabulary is None:
        output.stage_decision = output.stage_decision or output.decision
        return output
    if output.stage_decision:
        decision = output.stage_decision.lower()
        if decision not in vocabulary:
            raise ValueError(f"{role}: invalid published stage decision {decision!r}")
        output.stage_decision = decision
        output.decision = vocabulary[decision]  # type: ignore[assignment]
    else:
        # Old checkpoints and explicit command adapters remain readable. Preserve meaning.
        reverse = {v: k for k, v in vocabulary.items()}
        if output.decision not in reverse:
            raise ValueError(f"{role}: decision is not part of its published vocabulary")
        output.stage_decision = reverse[output.decision]
    return output
