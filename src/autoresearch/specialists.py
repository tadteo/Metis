"""Specialist workflows behind the runner's accounted model-call interface.

Dispatch returns a direct result or enriches caller-owned context for the ordinary
panel. This module never owns provider transport, caching or model reservations.
"""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from .catalog import AgentCatalog, AgentDefinition
from .coding import run_coding
from .config import ResearchConfig
from .contracts import AgentOutput, Evidence, RunState
from .inspection import inspect_code
from .laya import triage
from .literature import Literature
from .review import review_context
from .store import Store
from .writing import compose_manuscript


class AccountedCall(Protocol):
    """A runner call retaining routing, cache, validation and usage accounting."""

    def __call__(
        self,
        state: RunState,
        role: str,
        context: dict[str, Any],
        index: int,
        frontier: bool = False,
    ) -> AgentOutput: ...


class SpecialistDispatcher:
    def __init__(
        self,
        store: Store,
        config: ResearchConfig,
        catalog: AgentCatalog,
        literature: Literature | None = None,
    ) -> None:
        self.store, self.config, self.catalog = store, config, catalog
        self.literature = literature

    def dispatch(
        self,
        state: RunState,
        role: str,
        context: dict[str, Any],
        call: AccountedCall,
    ) -> AgentOutput | None:
        """Return a direct specialist result, or prepare context for the normal panel.

        The runner supplies a private context copy and validates direct scientific
        results. Typed advice retains its separate advisory-only output contract.
        Review preparation persists evidence before the ordinary panel is called.
        """
        definition = self.catalog.definition(role)
        if definition.handler == "typed_decision":
            return self._typed_advice(state, role, context)
        native = self.config.mode == "live" and role not in self.config.role_commands
        if native and definition.handler == "inspection":
            return self._inspect(state, role, context, call, definition)
        if (
            self.config.laya.enabled
            and self.config.mode == "live"
            and definition.advisory_agent is not None
        ):
            self._add_advice(state, role, context, definition.advisory_agent)
        if native and definition.handler == "coding":
            return self._code(state, role, context, call)
        if native and definition.handler == "writer":
            return self._write(state)
        if native and definition.handler == "review":
            self._prepare_review(state, context, call)
        return None

    def _typed_advice(self, state: RunState, role: str, context: dict[str, Any]) -> AgentOutput:
        result = (
            triage(
                self.store,
                state.id,
                role,
                self.config.laya,
                context,
                catalog=self.catalog,
                agent_role=role,
            )
            if self.config.mode == "live" and self.config.laya.enabled
            else {
                "available": False,
                "advisory_only": True,
                "escalate": True,
                "reason": "typed advisory model disabled",
            }
        )
        return AgentOutput(
            summary="Advisory triage requires scientific adjudication",
            decision="refine",
            structured=result,
        )

    def _inspect(
        self,
        state: RunState,
        role: str,
        context: dict[str, Any],
        call: AccountedCall,
        definition: AgentDefinition,
    ) -> AgentOutput:
        count = len(self.config.role_panels.get(role, [])) or (
            1
            if definition.panel == "single"
            else self.config.pipeline.critics
            if definition.panel == "critics"
            else self.config.pipeline.agents_per_role
        )

        def inspect(index: int) -> AgentOutput:
            return inspect_code(
                state,
                role,
                lambda subrole, ctx: call(
                    state, subrole, ctx, index, frontier=bool(ctx.get("escalate"))
                ),
                self.store,
                self.config,
                {
                    **context,
                    "reviewer_index": index,
                    "task": self.catalog.render(role, self.config.prompt_overrides.get(role, "")),
                },
                catalog=self.catalog,
            )

        with ThreadPoolExecutor(max_workers=min(count, self.config.pipeline.parallelism)) as pool:
            audits = list(pool.map(inspect, range(count)))
        selected = min(
            audits, key=lambda o: {"reject": 0, "refine": 1, "accept": 2}[o.decision]
        ).model_copy(deep=True)
        disagreement = len({o.decision for o in audits}) > 1
        uncertain = any(o.confidence < self.config.pipeline.escalation_confidence for o in audits)
        may_escalate = bool(self.config.frontier_provider) and (
            (disagreement and definition.escalation.on_disagreement)
            or (uncertain and definition.escalation.on_low_confidence)
        )
        if disagreement or uncertain:
            if may_escalate:
                selected = inspect_code(
                    state,
                    role,
                    lambda subrole, ctx: call(state, subrole, ctx, count, frontier=True),
                    self.store,
                    self.config,
                    {
                        **context,
                        "reviewer_index": count,
                        "task": self.catalog.render(
                            role, self.config.prompt_overrides.get(role, "")
                        ),
                        "panel": [o.model_dump() for o in audits],
                        "escalation_reason": "independent audit disagreement or insufficient confidence",
                    },
                    catalog=self.catalog,
                )
            if selected.decision == "accept" and (
                not may_escalate or selected.confidence < self.config.pipeline.escalation_confidence
            ):
                selected.decision = "refine"
                selected.feedback += "\nAudit confidence/disagreement remains unresolved."
        selected.structured["panel_outputs"] = [o.model_dump() for o in audits]
        self.store.event(
            state.id,
            "integrity_panel",
            state.stage,
            {
                "role": role,
                "decision": selected.decision,
                "outputs": [o.model_dump() for o in audits],
            },
        )
        return selected

    def _add_advice(
        self, state: RunState, role: str, context: dict[str, Any], advisory_agent: str
    ) -> None:
        context[advisory_agent] = triage(
            self.store,
            state.id,
            role,
            self.config.laya,
            {
                "role": role,
                "ideas": [{"id": i.id, "hypothesis": i.hypothesis} for i in state.ideas],
                "feedback": state.feedback,
            },
            catalog=self.catalog,
            agent_role=advisory_agent,
        )

    def _code(
        self, state: RunState, role: str, context: dict[str, Any], call: AccountedCall
    ) -> AgentOutput:
        output = run_coding(
            state,
            lambda subrole, ctx: call(state, subrole, ctx, 0, frontier=bool(ctx.get("escalate"))),
            self.store,
            self.config,
            {
                **context,
                "original_role": role,
                "role_instruction": self.catalog.render(
                    role, self.config.prompt_overrides.get(role, "")
                ),
                "tool_protocol": self.catalog.prompt("coding_step"),
                "history_access": self.catalog.text("prompts/history.md"),
                "catalog_digest": self.catalog.digest,
            },
        )
        return output

    def _write(self, state: RunState) -> AgentOutput:
        output, refs = compose_manuscript(
            state,
            store=self.store,
            config=self.config,
        )
        known = {e.id: e for e in state.evidence}
        known.update({e["id"]: Evidence.model_validate(e) for e in refs})
        state.evidence = list(known.values())
        return output

    def _review_literature(self, state: RunState) -> Literature:
        from . import behavior

        supplied = behavior.extension_manifest(
            {"literature": self.literature}, strict=self.config.mode == "live"
        ).get("literature")
        if state.behavior is not None:
            expected = behavior.recorded(self.store, state)["extensions"].get("literature")
            if supplied != expected:
                raise ValueError("review retrieval adapter differs from the pinned run behavior")
        return self.literature if self.literature is not None else Literature(self.config)

    def _prepare_review(
        self, state: RunState, context: dict[str, Any], call: AccountedCall
    ) -> None:
        literature = self._review_literature(state)
        attempt_id = uuid.uuid4().hex[:12]

        def checkpoint(snapshot: dict[str, Any]) -> None:
            artifact = self.store.artifact(
                state.id,
                "scholarpeer_checkpoint",
                f"scholarpeer-v{state.version}-{attempt_id}-c{snapshot['sequence']:04}.json",
                json.dumps(snapshot, indent=2),
            )
            self.store.event(
                state.id,
                "scholarpeer_checkpoint",
                state.stage,
                {
                    "attempt_id": attempt_id,
                    "sequence": snapshot["sequence"],
                    "status": snapshot["status"],
                    "event": snapshot["event"],
                    "artifact": artifact,
                },
            )

        reconstructed = review_context(
            state,
            lambda subrole, ctx: call(state, subrole, ctx, 0, frontier=bool(ctx.get("escalate"))),
            literature,
            self.config.pipeline.parallelism,
            self.catalog.text("prompts/review_adaptation.md"),
            checkpoint=checkpoint,
        )
        context.update(reconstructed)
        context["review_context_artifact"] = self.store.artifact(
            state.id,
            "scholarpeer_context",
            f"scholarpeer-v{state.version}.json",
            json.dumps(reconstructed, indent=2, default=str),
        )
        self.store.event(
            state.id,
            "literature_coverage",
            state.stage,
            {"coverage": reconstructed.get("literature_coverage", {})},
        )
        state.memory.append(
            {
                "kind": "review_context",
                "version": state.version,
                "publication_cutoff": reconstructed.get("publication_cutoff"),
                "artifact": f"scholarpeer-v{state.version}.json",
            }
        )
        known = {e.id: e for e in state.evidence}
        known.update(
            {e["id"]: Evidence.model_validate(e) for e in reconstructed["review_evidence"]}
        )
        state.evidence = list(known.values())
