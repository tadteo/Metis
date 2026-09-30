"""Trusted implementation registry for declarative workflow actions.

Specifications choose existing actions; they cannot import or execute arbitrary Python.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import experimentation, intake, integrity, manuscript, seeds

if TYPE_CHECKING:
    from ..agents import AgentRunner
    from ..config import ResearchConfig
    from ..contracts import RunState
    from ..engine import Engine

StageHandler = Callable[["Engine", "RunState", "ResearchConfig", "AgentRunner"], None]


@dataclass(frozen=True)
class StageAction:
    """Scientific/specialist entrypoints and known panel-selection dependencies.

    Optional advisory services and native upstream endpoints are declared by their
    agent definitions; these dependencies are not an inventory of HTTP endpoints.
    """

    handler: StageHandler
    agents: frozenset[str]


STAGE_AGENT = frozenset({"$stage"})
PRODUCER_AGENTS = STAGE_AGENT | {"artifact_selector"}
CODING_AGENTS = STAGE_AGENT | {"coding_step", "experiment_integrity", "inspection_step"}
REVIEW_AGENTS = STAGE_AGENT | {
    "review_summary",
    "review_literature",
    "review_expansion",
    "review_historian",
    "review_baseline_scout",
    "review_novelty_questions",
    "review_novelty_answers",
    "review_technical_questions",
    "review_technical_answers",
}
INTEGRITY_AGENTS = STAGE_AGENT | {
    "artifact_selector",
    "claim_extraction",
    "claim_coverage",
    "citation_entailment",
    "method_alignment",
    "inspection_step",
    "heldout_review",
}

# The stage placeholder reflects the common handlers' agents.run(state, state.stage)
# call. Specialist dependencies remain explicit even when configuration disables one.
ACTIONS: dict[str, StageAction] = {
    "intake.prepare": StageAction(intake.prepare, STAGE_AGENT),
    "seeds.extract_limitations": StageAction(seeds.extract_limitations, PRODUCER_AGENTS),
    "seeds.verify_limitations": StageAction(seeds.verify_limitations, STAGE_AGENT),
    "seeds.generate_ideas": StageAction(seeds.generate_ideas, STAGE_AGENT),
    "seeds.assess_novelty": StageAction(seeds.assess_novelty, STAGE_AGENT),
    "seeds.filter_ideas": StageAction(seeds.filter_ideas, STAGE_AGENT),
    "experimentation.criticize_candidate": StageAction(
        experimentation.criticize_candidate, STAGE_AGENT
    ),
    "seeds.evolve": StageAction(seeds.evolve, STAGE_AGENT),
    "experimentation.select_candidate": StageAction(experimentation.select_candidate, STAGE_AGENT),
    "experimentation.plan_supplementary": StageAction(
        experimentation.plan_supplementary, PRODUCER_AGENTS
    ),
    "experimentation.criticize_ablation": StageAction(
        experimentation.criticize_ablation, STAGE_AGENT
    ),
    "experimentation.compare_refinement": StageAction(
        experimentation.compare_refinement, STAGE_AGENT
    ),
    "manuscript.write_manuscript": StageAction(manuscript.write_manuscript, STAGE_AGENT),
    "manuscript.peer_review": StageAction(manuscript.peer_review, REVIEW_AGENTS),
    "manuscript.meta_review": StageAction(manuscript.meta_review, STAGE_AGENT),
    "manuscript.complete": StageAction(manuscript.complete, frozenset()),
    "experimentation.execute": StageAction(experimentation.execute, CODING_AGENTS),
    "integrity.finalize": StageAction(integrity.finalize, INTEGRITY_AGENTS),
}

HANDLERS: dict[str, StageHandler] = {name: action.handler for name, action in ACTIONS.items()}
