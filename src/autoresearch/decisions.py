"""Published stage-specific decisions with a legacy checkpoint migration boundary."""

from .catalog import AgentCatalog, load_catalog
from .contracts import AgentOutput

# Compatibility view: decision vocabulary is owned by each agent definition.
STAGE_DECISIONS = {
    role: agent.decisions for role, agent in load_catalog().agents.items() if agent.decisions
}


def normalize_decision(
    role: str, output: AgentOutput, catalog: AgentCatalog | None = None
) -> AgentOutput:
    vocabulary = (catalog or load_catalog()).definition(role).decisions
    if not vocabulary:
        output.stage_decision = output.stage_decision or output.decision
        return output
    if output.stage_decision:
        decision = output.stage_decision.lower()
        if decision not in vocabulary:
            raise ValueError(f"{role}: invalid published stage decision {decision!r}")
        output.stage_decision = decision
        output.decision = vocabulary[decision]
    else:
        # Old checkpoints and explicit command adapters remain readable. Preserve meaning.
        reverse = {v: k for k, v in vocabulary.items()}
        if output.decision not in reverse:
            raise ValueError(f"{role}: decision is not part of its published vocabulary")
        output.stage_decision = reverse[output.decision]
    return output
