"""Trusted implementation registry for declarative workflow actions.

Specifications choose existing actions; they cannot import or execute arbitrary Python.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from . import experimentation, integrity, manuscript, seeds

if TYPE_CHECKING:
    from ..agents import AgentRunner
    from ..config import ResearchConfig
    from ..contracts import RunState
    from ..engine import Engine

StageHandler = Callable[["Engine", "RunState", "ResearchConfig", "AgentRunner"], None]

HANDLERS: dict[str, StageHandler] = {
    "seeds.extract_limitations": seeds.extract_limitations,
    "seeds.verify_limitations": seeds.verify_limitations,
    "seeds.generate_ideas": seeds.generate_ideas,
    "seeds.assess_novelty": seeds.assess_novelty,
    "seeds.filter_ideas": seeds.filter_ideas,
    "experimentation.criticize_candidate": experimentation.criticize_candidate,
    "seeds.evolve": seeds.evolve,
    "experimentation.select_candidate": experimentation.select_candidate,
    "experimentation.plan_supplementary": experimentation.plan_supplementary,
    "experimentation.criticize_ablation": experimentation.criticize_ablation,
    "experimentation.compare_refinement": experimentation.compare_refinement,
    "manuscript.write_manuscript": manuscript.write_manuscript,
    "manuscript.peer_review": manuscript.peer_review,
    "manuscript.meta_review": manuscript.meta_review,
    "manuscript.complete": manuscript.complete,
    "experimentation.execute": experimentation.execute,
    "integrity.finalize": integrity.finalize,
}
