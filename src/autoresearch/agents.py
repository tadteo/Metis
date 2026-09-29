"""Independent agent panels, validated outputs, routing and explicit escalation."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import ValidationError

from .coding import CODING_ROLES, run_coding
from .config import ResearchConfig
from .contracts import (
    AgentOutput,
    AgentRequest,
    AgentResponse,
    Evidence,
    Idea,
    ProviderConfig,
    RunState,
    Usage,
)
from .decisions import normalize_decision
from .demo import DemoProvider
from .execution import _run
from .inspection import INSPECTION_ROLES, inspect_code
from .laya import triage
from .literature import Literature
from .privacy import redact
from .prompts import VERSION, system_prompt
from .providers import CompatibleProvider, Provider, ProviderError
from .review import retrieval_model_view, review_context
from .store import Store
from .writing import compose_manuscript

CRITICS = {
    "verify_limitations",
    "novelty",
    "filter_ideas",
    "subset_critic",
    "full_critic",
    "select",
    "ablation_critic",
    "compare",
    "peer_review",
    "meta_review",
    "integrity",
    "experiment_integrity",
    "claim_coverage",
    "citation_entailment",
    "method_alignment",
}
CHEAP_ROLES = {"filter_ideas", "novelty", "artifact_selector"}


class AgentRunner:
    def __init__(self, store: Store, config: ResearchConfig, provider: Provider | None = None):
        self.store, self.config, self.provider = store, config, provider

    def run(self, state: RunState, role: str, context: dict[str, Any] | None = None) -> AgentOutput:
        context = dict(context or {})
        if (
            role in INSPECTION_ROLES
            and self.config.mode == "live"
            and role not in self.config.role_commands
        ):
            count = len(self.config.role_panels.get(role, [])) or self.config.pipeline.critics

            def inspect(index: int) -> AgentOutput:
                return inspect_code(
                    state,
                    role,
                    lambda subrole, ctx: self._one(
                        state, subrole, ctx, index, frontier=bool(ctx.get("escalate"))
                    ),
                    self.store,
                    self.config,
                    {
                        **context,
                        "reviewer_index": index,
                        "task": system_prompt(role, self.config.prompt_overrides.get(role, "")),
                    },
                )

            with ThreadPoolExecutor(
                max_workers=min(count, self.config.pipeline.parallelism)
            ) as pool:
                audits = list(pool.map(inspect, range(count)))
            selected = min(
                audits, key=lambda o: {"reject": 0, "refine": 1, "accept": 2}[o.decision]
            ).model_copy(deep=True)
            if len({o.decision for o in audits}) > 1 or any(
                o.confidence < self.config.pipeline.escalation_confidence for o in audits
            ):
                if self.config.frontier_provider:
                    selected = inspect_code(
                        state,
                        role,
                        lambda subrole, ctx: self._one(state, subrole, ctx, count, frontier=True),
                        self.store,
                        self.config,
                        {
                            **context,
                            "reviewer_index": count,
                            "task": system_prompt(role, self.config.prompt_overrides.get(role, "")),
                            "panel": [o.model_dump() for o in audits],
                            "escalation_reason": "independent audit disagreement or insufficient confidence",
                        },
                    )
                if selected.decision == "accept" and (
                    not self.config.frontier_provider
                    or selected.confidence < self.config.pipeline.escalation_confidence
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
        if (
            self.config.laya.enabled
            and self.config.mode == "live"
            and role in {"filter_ideas", "artifact_selector"}
        ):
            context["laya_triage"] = triage(
                self.store,
                state.id,
                role,
                self.config.laya,
                {
                    "role": role,
                    "ideas": [{"id": i.id, "hypothesis": i.hypothesis} for i in state.ideas],
                    "feedback": state.feedback,
                },
            )
        if (
            role in CODING_ROLES
            and self.config.mode != "demo"
            and role not in self.config.role_commands
        ):
            return run_coding(
                state,
                lambda subrole, ctx: self._one(
                    state, subrole, ctx, 0, frontier=bool(ctx.get("escalate"))
                ),
                self.store,
                self.config,
                {**context, "original_role": role},
            )
        if (
            role in {"draft", "revise"}
            and self.config.mode != "demo"
            and role not in self.config.role_commands
        ):
            output, refs = compose_manuscript(
                state,
                store=self.store,
                config=self.config,
            )
            known = {e.id: e for e in state.evidence}
            known.update({e["id"]: Evidence.model_validate(e) for e in refs})
            state.evidence = list(known.values())
            return output
        if (
            role == "peer_review"
            and self.config.mode != "demo"
            and role not in self.config.role_commands
        ):
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
                lambda subrole, ctx: self._one(
                    state, subrole, ctx, 0, frontier=bool(ctx.get("escalate"))
                ),
                Literature(self.config),
                self.config.pipeline.parallelism,
                checkpoint,
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
        count = len(self.config.role_panels.get(role, [])) or (
            self.config.pipeline.critics
            if role in CRITICS
            else self.config.pipeline.agents_per_role
        )
        # Generators fan out; editors draft competing implementations which critics select.
        with ThreadPoolExecutor(max_workers=min(count, self.config.pipeline.parallelism)) as pool:
            outputs = list(
                pool.map(lambda index: self._one(state, role, context or {}, index), range(count))
            )
        generating = role in {"generate_ideas", "evolve"}
        disagreement = len({o.decision for o in outputs}) > 1
        uncertain = any(o.confidence < self.config.pipeline.escalation_confidence for o in outputs)
        selected = outputs[0].model_copy(deep=True)
        if role in CRITICS or generating:
            # A substantive objection cannot disappear in a majority vote.
            selected = min(
                outputs, key=lambda o: {"reject": 0, "refine": 1, "accept": 2}[o.decision]
            ).model_copy(deep=True)
            selected.confidence = min(o.confidence for o in outputs)
            selected.feedback = "\n".join(
                f"Reviewer {i + 1}: {o.feedback or o.summary}" for i, o in enumerate(outputs)
            )
            scores = [o.score for o in outputs if o.score is not None]
            if scores:
                selected.score = min(scores)
            if generating:
                selected.ideas = self._merged_ideas(state, outputs)
            if role == "novelty":
                ids = set.intersection(*(set(o.novelty_scores) for o in outputs))
                selected.novelty_scores = {
                    i: min(o.novelty_scores[i] for o in outputs) for i in ids
                }
            if role == "select" and len({o.selected_id for o in outputs}) > 1:
                disagreement = True
                selected.decision = "refine"
        if (disagreement or uncertain) and self.config.frontier_provider:
            selected = self._one(
                state,
                role,
                {
                    **context,
                    "panel": [o.model_dump() for o in outputs],
                    "escalation_reason": "disagreement" if disagreement else "uncertainty",
                },
                count,
                frontier=True,
            )
            if (
                selected.confidence < self.config.pipeline.escalation_confidence
                and selected.decision == "accept"
            ):
                selected.decision = "refine"
                selected.feedback += (
                    "\nFrontier review remains uncertain; further evidence is required."
                )
            if generating:
                selected.ideas = self._merged_ideas(state, [selected])
        elif disagreement or uncertain:
            if selected.decision == "accept":
                selected.decision = "refine"
            selected.feedback += (
                "\nUnresolved panel disagreement/uncertainty; no frontier provider configured."
            )
        elif not generating and role not in CRITICS and len(outputs) > 1:
            selection_context = {
                "original_role": role,
                "stage_context": context,
                "panel": {str(i): o.model_dump() for i, o in enumerate(outputs)},
                "artifact_selection": True,
            }
            selection = self._one(state, "artifact_selector", selection_context, 0)
            if (
                selection.confidence < self.config.pipeline.escalation_confidence
                and self.config.frontier_provider
            ):
                selection = self._one(
                    state,
                    "artifact_selector",
                    {
                        **selection_context,
                        "selection_review": selection.model_dump(),
                        "escalation_reason": "uncertainty",
                    },
                    1,
                    frontier=True,
                )
            if (
                selection.decision != "accept"
                or selection.confidence < self.config.pipeline.escalation_confidence
            ):
                raise ValueError(
                    "artifact selector did not confidently accept a candidate: "
                    + selection.feedback
                )
            try:
                selected_index = int(selection.selected_id or "-1")
                if not 0 <= selected_index < len(outputs):
                    raise ValueError("invalid selection index")
                selected = outputs[selected_index]
                if selected.decision != "accept":
                    raise ValueError("selected artifact is rejected or requires refinement")
            except (ValueError, IndexError) as exc:
                raise ValueError(
                    "artifact selector did not identify a valid accepted candidate"
                ) from exc
        if generating and selected.decision != "accept":
            # Proposals remain in private agent traces; unresolved proposals cannot be promoted.
            selected.ideas = []
        coverage = context.get("literature_coverage", {})
        if role == "peer_review" and coverage and not coverage.get("sufficient_for_assessment"):
            selected.decision = "refine"
            selected.concerns.append(
                "Insufficient retrieved literature coverage; novelty cannot be certified. See the persisted search reports."
            )
        self.store.event(
            state.id,
            "agent_consensus",
            state.stage,
            {
                "role": role,
                "agents": count,
                "decision": selected.decision,
                "disagreement": disagreement,
                "uncertain": uncertain,
                "selected_id": selected.selected_id,
                "idea_ids": [idea.id for idea in selected.ideas],
                "stage_decision": selected.stage_decision,
                "individual_outputs": [o.model_dump() for o in outputs],
            },
        )
        selected.structured["panel_outputs"] = [o.model_dump() for o in outputs]
        if role == "peer_review" and "individual_outputs" in context:
            # Complete prompt/transport provenance is immutable in the context
            # artifact. Keep all scientific findings available to later stages
            # without recursively duplicating raw retrieval and rendered prompts.
            selected.structured["review_context"] = {
                key: context[key]
                for key in (
                    "review_context_artifact",
                    "summary",
                    "historian",
                    "baseline_scout",
                    "qa_pairs",
                    "literature_coverage",
                    "publication_cutoff",
                    "prompt_provenance",
                    "review_guidelines",
                    "score_semantics",
                )
                if key in context
            }
        # Aggregation may have changed the compatibility verdict after a quality gate.
        selected.stage_decision = ""
        normalize_decision(role, selected)
        return selected

    @staticmethod
    def _merged_ideas(state: RunState, outputs: list[AgentOutput]) -> list[Idea]:
        merged: list[Idea] = []
        hypotheses = {" ".join(idea.hypothesis.split()).casefold() for idea in state.ideas}
        identifiers = {idea.id for idea in state.ideas}
        for panel, output in enumerate(outputs):
            for position, proposed in enumerate(output.ideas):
                fingerprint = " ".join(proposed.hypothesis.split()).casefold()
                if not fingerprint or fingerprint in hypotheses:
                    continue
                hypotheses.add(fingerprint)
                idea = proposed.model_copy(deep=True)
                original = f"{idea.id}-a{panel}" if len(outputs) > 1 else idea.id
                candidate = original
                collision = position
                while candidate in identifiers:
                    candidate = f"{original}-{collision}"
                    collision += 1
                idea.id = candidate
                identifiers.add(candidate)
                merged.append(idea)
        return merged

    def _one(
        self,
        state: RunState,
        role: str,
        context: dict[str, Any],
        index: int,
        frontier: bool = False,
    ) -> AgentOutput:
        cfg = self.config.role_providers.get(role, self.config.provider)
        original_role = (
            str(context.get("original_role", role))
            if role in {"coding_step", "inspection_step"}
            else role
        )
        if role in {"coding_step", "inspection_step"}:
            cfg = self.config.role_providers.get(original_role, cfg)
            if self.config.role_panels.get(original_role):
                panel = self.config.role_panels[original_role]
                cfg = panel[index % len(panel)]
        if role in self.config.role_panels and self.config.role_panels[role]:
            cfg = self.config.role_panels[role][index % len(self.config.role_panels[role])]
        if role == "heldout_review" and self.config.heldout_provider:
            cfg = self.config.heldout_provider
        if frontier and self.config.frontier_provider:
            cfg = self.config.frontier_provider
        elif (
            role not in self.config.role_providers
            and role not in self.config.role_panels
            and role in CHEAP_ROLES
            and self.config.cheap_provider
        ):
            cfg = self.config.cheap_provider
        semantic_state = state.model_dump(
            mode="json", exclude={"version", "created_at", "updated_at", "status", "error"}
        )
        semantic_state["reviews"] = [
            review
            for review in semantic_state["reviews"]
            if review.get("kind") != "heldout" and review.get("optimization_feedback") is not False
        ]
        if role == "heldout_review":
            semantic_state = {
                k: semantic_state[k]
                for k in (
                    "id",
                    "title",
                    "objective",
                    "manuscript",
                    "evidence",
                    "experiments",
                    "selected_idea",
                )
            }
        ctx = {
            "state": semantic_state,
            "project": self.config.project.model_dump(),
            "reviewer_perspective": [
                "methodological rigor",
                "reproducibility and leakage",
                "novelty and competing explanations",
                "robustness and uncertainty",
            ][index % 4],
            **context,
        }
        ctx = redact(retrieval_model_view(ctx), self.config.privacy.redact_patterns)
        request = AgentRequest(
            run_id=state.id,
            stage=state.stage,
            role=role,
            system=str(
                redact(
                    system_prompt(role, self.config.prompt_overrides.get(role, "")),
                    self.config.privacy.redact_patterns,
                )
            ),
            prompt=json.dumps(ctx),
            schema_version=VERSION,
        )
        key = hashlib.sha256(
            json.dumps(
                {
                    "run": state.id,
                    "request": request.model_dump(),
                    "provider": cfg.model_dump(),
                    "index": index,
                    "adapter": self.config.role_commands.get(role),
                    "adapter_budget": self.config.role_command_max_cost_usd.get(role),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        request.cache_key = key
        cached = self.store.cache_get(key) if self.config.privacy.cache else None
        if cached:
            self.store.event(state.id, "agent_cache", state.stage, {"role": role, "key": key})
            return normalize_decision(role, AgentOutput.model_validate(cached))
        provider: Provider = self.provider or (
            DemoProvider() if self.config.mode == "demo" else CompatibleProvider(cfg)
        )
        for attempt in range(self.config.pipeline.max_agent_repairs + 1):
            self.store.event(
                state.id,
                "agent_started",
                state.stage,
                {
                    "role": role,
                    "agent": index,
                    "model": cfg.model if self.config.mode != "demo" else "offline-fixture",
                    "prompt": request.prompt,
                    "system": request.system,
                    "prompt_sha256": key,
                    "attempt": attempt,
                },
            )
            if role in self.config.role_commands:
                if role not in self.config.role_command_max_cost_usd:
                    raise ValueError(
                        "external role adapter requires an explicit role_command_max_cost_usd cap"
                    )
                maximum = self.config.role_command_max_cost_usd[role]
            else:
                maximum = 0.0 if self.config.mode == "demo" else self._reservation(cfg, request)
            call_id = self.store.reserve(state.id, role, maximum, key)
            try:
                if role in self.config.role_commands:
                    response = self._command(role, request, cfg, maximum)
                else:
                    response = provider.complete(request)
            except ProviderError as exc:
                self.store.settle(call_id, exc.usage)
                raise
            except Exception:
                # Unknown remote completion state: conservatively charge reservation until audited.
                self.store.settle(call_id, Usage(cost_usd=maximum, estimated=True))
                raise
            self.store.settle(call_id, response.usage)
            if role in self.config.role_commands and response.usage.cost_usd > maximum:
                raise ValueError(
                    "external role adapter exceeded its declared cost cap; actual reported usage was charged"
                )
            self.store.event(
                state.id,
                "agent_completed",
                state.stage,
                {
                    "role": role,
                    "agent": index,
                    "model": response.model,
                    "provider": response.provider,
                    "output": response.data,
                    "usage": response.usage.model_dump(),
                },
            )
            try:
                output = normalize_decision(role, AgentOutput.model_validate(response.data))
            except (ValidationError, ValueError):
                if attempt >= self.config.pipeline.max_agent_repairs:
                    if not frontier and self.config.frontier_provider:
                        return self._one(
                            state,
                            role,
                            {
                                **context,
                                "escalation_reason": "structured output failed the defined schema after repairs",
                            },
                            index,
                            frontier=True,
                        )
                    raise ValueError(
                        f"{role}: invalid structured output after repair budget"
                    ) from None
                request.prompt = json.dumps(
                    {
                        **ctx,
                        "repair": "Previous output violated the JSON schema. Return correctly typed required fields; do not invent evidence.",
                    }
                )
                continue
            if self.config.privacy.cache:
                self.store.cache_put(key, output.model_dump())
            return output
        raise RuntimeError("agent validation exhausted")

    @staticmethod
    def _reservation(config: ProviderConfig, request: AgentRequest) -> float:
        tokens = len(request.system.encode()) + len(request.prompt.encode()) + 256
        return (
            (
                tokens * max(config.input_per_million, config.long_input_per_million)
                + config.max_output_tokens
                * max(config.output_per_million, config.long_output_per_million)
            )
            / 1e6
            * (config.retries + 1)
        )

    def _command(
        self, role: str, request: AgentRequest, cfg: ProviderConfig, maximum: float
    ) -> AgentResponse:
        argv = self.config.role_commands[role]
        if not argv or any("\0" in arg for arg in argv):
            raise ValueError("invalid configured adapter argv")
        # Operator-owned adapters are trusted programs; they must honor the explicit cost cap.
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "SYSTEMROOT"}}
        if cfg.api_key_env in os.environ:
            env[cfg.api_key_env] = os.environ[cfg.api_key_env]
        env.update(
            AUTORESEARCH_MAX_COST_USD=str(maximum),
            AUTORESEARCH_MODEL=cfg.model,
            AUTORESEARCH_BASE_URL=cfg.base_url,
            AUTORESEARCH_API_KEY_ENV=cfg.api_key_env,
        )
        limit = min(8_000_000, self.config.execution.max_log_bytes)
        done = _run(
            argv,
            cwd=self.store.run_dir(request.run_id),
            env=env,
            timeout=min(600, cfg.timeout_seconds),
            limit=limit,
            input_data=request.model_dump_json().encode(),
        )
        if (
            done.timed_out
            or done.returncode
            or len(done.stdout.encode()) > limit
            or len(done.stderr.encode()) > limit
        ):
            raise ValueError("external role adapter failed, timed out, or exceeded output limit")
        try:
            return AgentResponse.model_validate_json(done.stdout)
        except ValidationError:
            raise ValueError("external role adapter returned invalid response JSON") from None
