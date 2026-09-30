"""The initial agent shares the ordinary run's accounting and checkpoint lifecycle."""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from ..coding import CodingAction, CodingPending, CodingSession
from ..contracts import Evidence, Stage
from ..research_inputs import ResearchBrief, save_brief

if TYPE_CHECKING:
    from ..agents import AgentRunner
    from ..config import ResearchConfig
    from ..contracts import RunState
    from ..engine import Engine


def prepare(engine: Engine, state: RunState, config: ResearchConfig, agents: AgentRunner) -> None:
    session = CodingSession(
        state,
        lambda role, context: agents.run(state, role, context),
        engine.store,
        config,
        {
            "source_dir": str(engine.store.run_dir(state.id) / "source"),
            "original_role": "intake",
            "input_revision": state.input_revision,
            "role_instruction": agents.catalog.render("intake"),
        },
    )
    record = session.record
    # Restore successful retrievals even when a process stopped before the stage checkpoint.
    known = {e.id: e for e in state.evidence}
    for item in record.get("intake_evidence", []):
        evidence = Evidence.model_validate(item)
        known[evidence.id] = evidence
    state.evidence = list(known.values())
    literature = agents._review_literature(state)
    for _ in range(config.coding.max_steps - len(record["steps"])):
        if time.time() - record["created_at"] > config.coding.wall_seconds:
            raise ValueError("Research intake tool deadline reached; discovery retained")
        if (
            time.time() - datetime.fromisoformat(state.created_at).timestamp()
            > config.budget.wall_seconds
        ):
            from ..store import BudgetExceeded

            raise BudgetExceeded("Project wall-clock budget reached during intake")
        if engine.store.is_paused(state.id):
            raise CodingPending("Research intake paused")
        if record.get("completed"):
            brief = ResearchBrief.model_validate(record["completed"])
            break
        output = agents.run(state, "intake", session._context())
        try:
            action_data = output.plans[0]
            if action_data.get("tool") == "finish":
                brief = ResearchBrief.model_validate(
                    {
                        key: value
                        for key, value in output.structured.items()
                        if key != "panel_outputs"
                    }
                )
                if brief.outcome == "grounded":
                    if not record.get("intake_searched"):
                        raise ValueError("Search related literature before grounding the task")
                    by_id = {e.id: e for e in state.evidence}
                    if any(identifier not in by_id for identifier in brief.sources):
                        raise ValueError("Brief cites a source that was not retrieved")
                    if not any(
                        by_id[key].full_text or by_id[key].abstract for key in brief.sources
                    ):
                        raise ValueError("Read source content before grounding the task")
                record["completed"] = brief.model_dump()
                session.save()
                break
            if action_data.get("tool") == "discover":
                query = action_data.get("query", "")
                if not isinstance(query, str) or not query.strip() or len(query) > 4000:
                    raise ValueError("A focused literature query is required")
                found = literature.search(query, min(int(action_data.get("limit", 5)), 10))
                known = {e.id: e for e in state.evidence}
                for item in found:
                    inspected = literature.inspect(item) if not item.full_text else item
                    known[inspected.id] = inspected
                state.evidence = list(known.values())
                record["intake_evidence"] = [e.model_dump() for e in state.evidence]
                record["intake_searched"] = True
                observation = {
                    "evidence": record["intake_evidence"],
                    "retrieval": literature.last_report,
                }
            else:
                action = CodingAction.model_validate(action_data)
                if action.tool not in {"list", "read", "search", "history"}:
                    raise ValueError(
                        "Intake may inspect resources; implementation belongs to baseline coding"
                    )
                observation = session.observation(action)
        except (ValueError, OSError, IndexError) as error:
            observation = {"error": str(error)}
        record["steps"].append({"action": output.plans, "observation": observation})
        session.save()
        engine.store.event(state.id, "intake_observation", state.stage, record["steps"][-1])
    else:
        brief = ResearchBrief(
            outcome="unresolved",
            question="Research discovery reached its tool limit. Review the evidence and clarify the task before resuming.",
        )
    save_brief(engine.store, state, brief)
    if brief.outcome == "grounded":
        state.stage = Stage.LIMITATIONS
    else:
        state.feedback = brief.question
        state.status = "paused"
        engine.store.set_paused(state.id, True)
