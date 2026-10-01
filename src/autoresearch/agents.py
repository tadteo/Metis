"""Independent agent panels, validated outputs, routing and explicit escalation."""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from .catalog import AgentCatalog, load_catalog
from .config import ResearchConfig
from .contracts import (
    AgentOutput,
    AgentRequest,
    AgentResponse,
    Idea,
    Model,
    ProviderConfig,
    RunState,
    Usage,
)
from .credentials import resolve
from .decisions import normalize_decision
from .demo import DemoProvider
from .evidence_context import retrieval_model_view
from .literature import Literature
from .memory import research_view
from .privacy import redact
from .providers import CompatibleProvider, Provider, ProviderError
from .routing import ResolvedRoute, fallback_routes, resolve_route
from .runtime_support import run_process as _run
from .specialists import SpecialistDispatcher
from .store import Store


class CachedAgentResult(Model):
    """Validated output and the actual successful call, separate from its lookup key."""

    cache_format: Literal["agent_response.v1"] = "agent_response.v1"
    output: AgentOutput
    model: str
    provider: str
    call_id: str
    provenance: dict[str, str]


class AgentRunner:
    def __init__(
        self,
        store: Store,
        config: ResearchConfig,
        provider: Provider | None = None,
        *,
        catalog: AgentCatalog | None = None,
        literature: Literature | None = None,
    ):
        self.store, self.config, self.provider = store, config, provider
        self.literature = literature
        self._unavailable: dict[tuple[str, str, str], float] = {}
        specification_dir = config.specification_dir
        self.catalog = catalog or load_catalog(
            Path(specification_dir) if specification_dir else None
        )
        configured = (
            (set(config.role_providers) - set(self.catalog.models.upstream_slots))
            | set(config.role_panels)
            | set(config.role_commands)
            | set(config.prompt_overrides)
        )
        for role in configured:
            definition = self.catalog.definition(role)
            if definition.handler == "typed_decision":
                resolve_route(config, role, catalog=self.catalog)

    def _validated(
        self, role: str, output: AgentOutput, context: dict[str, Any] | None = None
    ) -> AgentOutput:
        return self.catalog.validate_output(
            role, normalize_decision(role, output, self.catalog), context
        )

    def run(self, state: RunState, role: str, context: dict[str, Any] | None = None) -> AgentOutput:
        definition = self.catalog.definition(role)
        context = dict(context or {})
        specialized = SpecialistDispatcher(
            self.store, self.config, self.catalog, self.literature
        ).dispatch(state, role, context, self._one)
        if specialized is not None:
            # Typed advice is not a scientific verdict and has its own contract.
            if definition.handler == "typed_decision":
                return specialized
            return self._validated(role, specialized, context)
        count = len(self.config.role_panels.get(role, [])) or (
            self.config.pipeline.critics
            if definition.panel == "critics"
            else 1
            if definition.panel == "single"
            else self.config.pipeline.agents_per_role
        )
        # Generators fan out; editors draft competing implementations which critics select.
        with ThreadPoolExecutor(max_workers=min(count, self.config.pipeline.parallelism)) as pool:
            outputs = list(
                pool.map(lambda index: self._one(state, role, context or {}, index), range(count))
            )
        generating = definition.aggregation == "merge_ideas"
        disagreement = len({o.decision for o in outputs}) > 1
        uncertain = any(o.confidence < self.config.pipeline.escalation_confidence for o in outputs)
        selected = outputs[0].model_copy(deep=True)
        if definition.aggregation == "conservative" or generating:
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
        if (
            (disagreement and definition.escalation.on_disagreement)
            or (uncertain and definition.escalation.on_low_confidence)
        ) and self.config.frontier_provider:
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
        elif definition.aggregation == "artifact_selection" and len(outputs) > 1:
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
        return self._validated(role, selected, context)

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
        from .coding import CodingPending
        from .model_inventory import identity

        definition = self.catalog.definition(role)
        original_role = str(context.get("original_role", role))
        route = resolve_route(self.config, role, index, original_role, frontier, self.catalog)
        original_definition = self.catalog.definition(original_role)
        protected = (
            self.provider is not None
            or self.config.mode != "live"
            or frontier
            or definition.context_policy == "heldout"
            or definition.model_policy == "heldout"
            or original_definition.context_policy == "heldout"
            or original_definition.model_policy == "heldout"
            or role in self.config.role_commands
            or original_role in self.config.role_commands
            or role in self.config.role_panels
            or original_role in self.config.role_panels
        )
        routes = [route] if protected else fallback_routes(self.config, route)
        if len(routes) == 1:
            try:
                return self._one_attempt(state, role, context, index, frontier, route)
            except ProviderError as error:
                if protected:
                    # A failed protected escalation must not trigger the caller's fallback.
                    error.recoverable = False
                raise
        last_error = None
        for candidate in routes:
            if self.store.is_paused(state.id):
                raise CodingPending("Model fallback paused at operator request")
            key = identity(candidate.provider)
            if self._unavailable.get(key, 0) > time.monotonic():
                continue
            if candidate is not route:
                self.store.event(
                    state.id,
                    "provider_fallback",
                    state.stage,
                    {
                        "role": role,
                        "agent": index,
                        "from_model": route.provider.model,
                        "to_model": candidate.provider.model,
                        "reason": str(last_error)
                        if last_error
                        else "Recent provider failure in this stage",
                    },
                )
            # A reservation represents one transport attempt, including failed ones.
            cfg = candidate.provider.model_copy(update={"retries": 0}, deep=True)
            try:
                return self._one_attempt(
                    state, role, context, index, frontier, ResolvedRoute(cfg, candidate.reason)
                )
            except ProviderError as error:
                if not error.recoverable:
                    raise
                last_error = error
                # ponytail: cooldown is shared within this runner/stage; in-flight calls finish.
                # Cross-worker health tracking is unnecessary for the current stage lease model.
                self._unavailable[key] = time.monotonic() + 60
        if last_error is not None:
            raise last_error
        raise ProviderError(
            "Permitted models are cooling down after provider failures; retry later"
        )

    def _one_attempt(
        self,
        state: RunState,
        role: str,
        context: dict[str, Any],
        index: int,
        frontier: bool,
        route: ResolvedRoute,
    ) -> AgentOutput:
        definition = self.catalog.definition(role)
        if definition.handler == "typed_decision":
            raise ValueError("typed decisions must use their dedicated transport")
        cfg = route.provider
        semantic_state = research_view(state, heldout=definition.context_policy == "heldout")
        ctx = {
            "state": semantic_state,
            "project": self.config.project.model_dump(),
            "reviewer_perspective": self.catalog.models.perspectives[
                index % len(self.catalog.models.perspectives)
            ],
            **context,
        }
        # Choose canonical reference targets only after privacy may remove fields.
        ctx = retrieval_model_view(
            redact(ctx, self.config.privacy.redact_patterns),
            deduplicate=True,
        )
        request = AgentRequest(
            run_id=state.id,
            stage=state.stage,
            role=role,
            system=str(
                redact(
                    self.catalog.render(role, self.config.prompt_overrides.get(role, "")),
                    self.config.privacy.redact_patterns,
                )
            ),
            prompt=json.dumps(ctx),
            schema_version=definition.output_schema,
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
                    "catalog_digest": self.catalog.digest,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        request.cache_key = key
        cached = self.store.cache_get(key) if self.config.privacy.cache else None
        if cached:
            if "cache_format" in cached:
                result = CachedAgentResult.model_validate(cached)
                output = self._validated(role, result.output, context)
                producing_call: dict[str, Any] = {
                    **result.provenance,
                    "model": result.model,
                    "provider": result.provider,
                    "call_id": result.call_id,
                    "provenance_status": "recorded",
                }
            else:
                # Old cache entries retain only scientific output. Configuration
                # cannot recover the actual provider or successful repair request.
                output = self._validated(role, AgentOutput.model_validate(cached), context)
                producing_call = {
                    "model": None,
                    "provider": None,
                    "call_id": None,
                    "provenance_status": "legacy_unknown",
                }
            self.store.event(
                state.id,
                "agent_cache",
                state.stage,
                {
                    **producing_call,
                    "role": role,
                    "key": key,
                    "lookup_request_sha256": hashlib.sha256(
                        request.model_dump_json(exclude={"cache_key", "provenance"}).encode()
                    ).hexdigest(),
                    "configured_route": route.reason,
                    "configured_model": cfg.model,
                    "configured_provider": cfg.name,
                },
            )
            return output
        provider: Provider = self.provider or (
            DemoProvider() if self.config.mode == "demo" else CompatibleProvider(cfg)
        )
        for attempt in range(self.config.pipeline.max_agent_repairs + 1):
            request_hash = hashlib.sha256(
                request.model_dump_json(exclude={"cache_key", "provenance"}).encode()
            ).hexdigest()
            behavior = state.behavior
            provenance = {
                "catalog_sha256": self.catalog.digest,
                "agent_version": definition.version,
                "agent_sha256": hashlib.sha256(definition.model_dump_json().encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(request.system.encode()).hexdigest(),
                "request_sha256": request_hash,
                "route": route.reason,
                "schema_version": definition.output_schema,
                "bundle_sha256": behavior.bundle_sha256 if behavior else "unbound",
            }
            request.provenance = provenance
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
                    **provenance,
                    "cache_key": key,
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
            call_id = self.store.reserve(state.id, role, maximum, request_hash)
            try:
                if role in self.config.role_commands:
                    response = self._command(role, request, cfg, maximum)
                else:
                    response = provider.complete(request)
            except ProviderError as exc:
                self.store.settle(call_id, exc.usage)
                self.store.event(
                    state.id,
                    "agent_provider_failed",
                    state.stage,
                    {
                        "role": role,
                        "agent": index,
                        "model": cfg.model,
                        "provider": cfg.name,
                        "call_id": call_id,
                        "error": str(exc),
                        "recoverable": exc.recoverable,
                        "usage": exc.usage.model_dump(),
                        **provenance,
                    },
                )
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
                    **provenance,
                    "call_id": call_id,
                },
            )
            try:
                output = self._validated(role, AgentOutput.model_validate(response.data), context)
            except (ValidationError, ValueError) as error:
                if attempt >= self.config.pipeline.max_agent_repairs:
                    if (
                        not frontier
                        and self.config.frontier_provider
                        and definition.escalation.on_invalid_output
                    ):
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
                        "repair": self.catalog.text("prompts/repair.md"),
                        "validation_issue": str(error),
                    }
                )
                continue
            if self.config.privacy.cache:
                self.store.cache_put(
                    key,
                    CachedAgentResult(
                        output=output,
                        model=response.model,
                        provider=response.provider,
                        call_id=call_id,
                        provenance=provenance,
                    ).model_dump(mode="json"),
                )
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
        key, _ = resolve(cfg.api_key_env)
        if key:
            env[cfg.api_key_env] = key
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
