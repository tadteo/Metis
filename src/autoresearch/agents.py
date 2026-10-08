"""Independent agent panels, validated outputs, routing and explicit escalation."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import ValidationError

from .catalog import AgentCatalog, load_catalog
from .config import ResearchConfig
from .contracts import (
    AgentOutput,
    AgentRequest,
    AgentResponse,
    Idea,
    Model,
    ModelQuotaExhaustion,
    ProviderConfig,
    RunState,
    Usage,
)
from .credentials import resolve
from .decisions import normalize_decision
from .demo import DemoProvider
from .evidence_context import evidence_focus, evidence_view_summary, retrieval_model_view
from .literature import Literature
from .memory import research_view
from .privacy import redact
from .providers import (
    CompatibleProvider,
    Provider,
    ProviderError,
    RequestTooLarge,
    request_input_bound,
)
from .routing import ResolvedRoute, fallback_routes, model_limits, resolve_route
from .runtime_support import run_process as _run
from .specialists import SpecialistDispatcher
from .store import Store, now

# Approximate bytes per token for the optional pre-dispatch size guard. Deliberately
# not the byte-per-token bound used for reservations, which would reject requests
# that fit; a model is skipped only when this typical estimate already exceeds a limit.
BYTES_PER_TOKEN = 4


def quota_key(provider: ProviderConfig) -> str:
    """Stable RunState key for a model identity (endpoint, model, key reference)."""
    from .model_inventory import identity

    return "|".join(identity(provider))


def _current() -> datetime:
    return _moment(now()) or datetime.now(UTC)


def _moment(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


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
        # Retry hint (or None) for models whose latest recoverable failure was HTTP 429.
        self._rate_limited: dict[tuple[str, str, str], float | None] = {}
        # Set by the engine for a quota-wait probe: one transport attempt per call.
        self.single_attempt = False
        # Long-window exhaustion recorded by this runner; also written into RunState.
        self._quota_lock = threading.Lock()
        self._exhausted: dict[str, ModelQuotaExhaustion] = {}
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

    def _take_single_attempt(self) -> bool:
        """Consume the post-wait probe flag: only the first dispatch is a single attempt."""
        with self._quota_lock:
            single, self.single_attempt = self.single_attempt, False
        return single

    def quota_exhaustions(self) -> dict[str, ModelQuotaExhaustion]:
        """Exhaustion records from this runner, for the engine to persist in RunState."""
        with self._quota_lock:
            return dict(self._exhausted)

    def _exhausted_until(self, state: RunState, provider: ProviderConfig) -> datetime | None:
        """Reset time of a model's exhausted long-window quota, or None when usable."""
        key = quota_key(provider)
        with self._quota_lock:
            records = [self._exhausted.get(key), state.model_quota_exhausted.get(key)]
        moments = [m for r in records if r is not None and (m := _moment(r.until))]
        latest = max(moments, default=None)
        return latest if latest is not None and latest > _current() else None

    def _pool_exhausted(self, state: RunState) -> dict[tuple[str, str, str], datetime]:
        """Exhausted models of the run's frozen permitted pool and their reset times."""
        from .model_inventory import identity

        inventory = self.config.model_inventory
        result: dict[tuple[str, str, str], datetime] = {}
        for entry in inventory.models if inventory is not None else []:
            if not entry.enabled or (
                self.config.allowed_models is not None
                and entry.id not in self.config.allowed_models
            ):
                continue
            until = self._exhausted_until(state, entry.provider)
            if until is not None:
                result[identity(entry.provider)] = until
        return result

    def _record_exhaustion(
        self, state: RunState, role: str, cfg: ProviderConfig, error: ProviderError
    ) -> None:
        if _moment(error.quota_exhausted_until) is None:
            return
        quota = error.quota
        record = ModelQuotaExhaustion(
            model=cfg.model,
            provider=cfg.name,
            until=error.quota_exhausted_until,
            window=quota.get("window", "long"),
            quota_id=quota.get("quota_id", ""),
            quota_value=quota.get("quota_value", ""),
            quota_metric=quota.get("quota_metric", ""),
            recorded_at=now(),
        )
        key = quota_key(cfg)
        with self._quota_lock:
            self._exhausted[key] = record
            state.model_quota_exhausted[key] = record
        self.store.event(
            state.id,
            "model_quota_exhausted",
            state.stage,
            {
                "role": role,
                **record.model_dump(),
                "retry_after_seconds": error.retry_after_seconds,
            },
        )

    def _exhausted_error(
        self,
        state: RunState,
        role: str,
        index: int,
        route: ResolvedRoute,
        until: datetime,
        protected: bool,
    ) -> ProviderError:
        """No request is sent to a model whose long-window quota is known to be exhausted."""
        remaining = max(0.0, (until - _current()).total_seconds())
        self.store.event(
            state.id,
            "model_quota_skipped",
            state.stage,
            {
                "role": role,
                "agent": index,
                "model": route.provider.model,
                "until": until.isoformat(),
                "protected": protected,
            },
        )
        detail = (
            "this route is fixed and is not swapped to another model"
            if protected
            else "no other permitted model is available"
        )
        return ProviderError(
            f"Model {route.provider.model} quota exhausted until "
            f"{until.isoformat(timespec='seconds')}; {detail}",
            recoverable=not protected,
            rate_limited=True,
            retry_after_seconds=remaining,
            model=route.provider.model,
            quota_exhausted_until=until.isoformat(),
        )

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
        # Long-window quota exhaustion persists in RunState across stages and restarts.
        pool_exhausted = {} if protected else self._pool_exhausted(state)
        routes = [route] if protected else fallback_routes(self.config, route, set(pool_exhausted))
        if len(routes) == 1:
            # External command roles never call the provider; quota does not apply.
            command = role in self.config.role_commands
            until = None if command else self._exhausted_until(state, route.provider)
            if until is not None:
                # Every permitted model is exhausted (or the route is fixed): report the
                # earliest reset so a quota wait resumes exactly when one becomes usable.
                earliest = min([until, *pool_exhausted.values()])
                raise self._exhausted_error(state, role, index, route, earliest, protected)
            try:
                return self._one_attempt(
                    state,
                    role,
                    context,
                    index,
                    frontier,
                    route,
                    single_attempt=self._take_single_attempt(),
                )
            except ProviderError as error:
                if protected:
                    # A failed protected escalation must not trigger the caller's fallback.
                    error.recoverable = False
                moment = _moment(error.quota_exhausted_until)
                if moment is not None and pool_exhausted:
                    # Another permitted model may reset before this one.
                    earliest = min([moment, *pool_exhausted.values()])
                    error.quota_exhausted_until = earliest.isoformat()
                    error.retry_after_seconds = max(0.0, (earliest - _current()).total_seconds())
                raise
        last_error: ProviderError | None = None
        skipped = ""
        exhausted: dict[tuple[str, str, str], datetime] = {}
        unfit: set[tuple[str, str, str]] = set()
        for candidate in routes:
            if self.store.is_paused(state.id):
                raise CodingPending("Model fallback paused at operator request")
            key = identity(candidate.provider)
            until = self._exhausted_until(state, candidate.provider)
            if until is not None:
                exhausted[key] = until
                skipped = (
                    f"Model {candidate.provider.model} quota exhausted until "
                    f"{until.isoformat(timespec='seconds')}"
                )
                continue
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
                        else skipped or "Recent provider failure in this stage",
                    },
                )
            # A reservation represents one transport attempt, including failed ones.
            # A pending probe is already a single attempt here; consume the flag.
            self._take_single_attempt()
            cfg = candidate.provider.model_copy(update={"retries": 0}, deep=True)
            try:
                output = self._one_attempt(
                    state, role, context, index, frontier, ResolvedRoute(cfg, candidate.reason)
                )
                self._rate_limited.pop(key, None)
                return output
            except RequestTooLarge as error:
                # Never sent; another model with larger limits may still fit.
                last_error = error
                unfit.add(key)
                continue
            except ProviderError as error:
                if not error.recoverable:
                    raise
                last_error = error
                if (moment := _moment(error.quota_exhausted_until)) is not None:
                    exhausted[key] = moment
                # ponytail: cooldown is shared within this runner/stage; in-flight calls finish.
                # Cross-worker health tracking is unnecessary for the current stage lease model.
                self._unavailable[key] = time.monotonic() + 60
                if error.rate_limited:
                    self._rate_limited[key] = error.retry_after_seconds
                else:
                    self._rate_limited.pop(key, None)
        keys = {identity(candidate.provider) for candidate in routes} - unfit
        if not keys:
            # Waiting cannot make an oversized request fit: block with a clear reason.
            raise ProviderError(
                "Request exceeds the declared token limits of every permitted model; "
                f"none was called ({last_error})",
                model=route.provider.model,
            )
        # Quota waiting applies only when every usable route is rate limited or exhausted.
        limited = all(key in self._rate_limited or key in exhausted for key in keys)
        current = _current()
        resets = {
            key: max(0.0, (moment - current).total_seconds())
            for key, moment in {**pool_exhausted, **exhausted}.items()
        }
        hints = [resets[key] if key in resets else self._rate_limited.get(key) for key in keys]
        # Earliest route availability; unknown if any limited route gave no hint.
        # Other exhausted pool models may reset sooner than these routes.
        hint = (
            min([*(value for value in hints if value is not None), *resets.values()])
            if limited and hints and None not in hints
            else None
        )
        reset_at = ""
        if limited and keys <= exhausted.keys():
            reset_at = min([*exhausted.values(), *pool_exhausted.values()]).isoformat()
        if last_error is not None:
            last_error.rate_limited = limited
            last_error.retry_after_seconds = hint if limited else None
            last_error.quota_exhausted_until = reset_at
            raise last_error
        raise ProviderError(
            "Permitted models are cooling down or quota-exhausted after provider failures; "
            "retry later",
            rate_limited=limited,
            retry_after_seconds=hint,
            model=route.provider.model,
            quota_exhausted_until=reset_at,
        )

    def _one_attempt(
        self,
        state: RunState,
        role: str,
        context: dict[str, Any],
        index: int,
        frontier: bool,
        route: ResolvedRoute,
        *,
        single_attempt: bool = False,
    ) -> AgentOutput:
        definition = self.catalog.definition(role)
        if definition.handler == "typed_decision":
            raise ValueError("typed decisions must use their dedicated transport")
        cfg = route.provider
        # A probe uses one transport attempt; the cache key keeps the configured route.
        transport = cfg.model_copy(update={"retries": 0}, deep=True) if single_attempt else cfg
        semantic_state = research_view(state, heldout=definition.context_policy == "heldout")
        ctx = {
            "state": semantic_state,
            "project": self.config.project.model_dump(),
            "reviewer_perspective": self.catalog.models.perspectives[
                index % len(self.catalog.models.perspectives)
            ],
            **context,
        }
        # Choose canonical reference targets and passage windows only after privacy
        # may remove fields. Stored evidence stays complete; only this view is bounded.
        redacted = redact(ctx, self.config.privacy.redact_patterns)
        focus, priority = evidence_focus(
            redacted["state"] if isinstance(redacted.get("state"), dict) else {},
            {key: value for key, value in redacted.items() if key in context},
        )
        ctx = retrieval_model_view(redacted, deduplicate=True, focus=focus, priority_ids=priority)
        evidence_view = evidence_view_summary(ctx)
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
            split_context=True,
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
            DemoProvider() if self.config.mode == "demo" else CompatibleProvider(transport)
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
            if self.config.mode != "demo" and role not in self.config.role_commands:
                self._guard_size(state, role, index, cfg, request)
            if role in self.config.role_commands:
                if role not in self.config.role_command_max_cost_usd:
                    raise ValueError(
                        "external role adapter requires an explicit role_command_max_cost_usd cap"
                    )
                maximum = self.config.role_command_max_cost_usd[role]
            else:
                maximum = (
                    0.0 if self.config.mode == "demo" else self._reservation(transport, request)
                )
            call_id = self.store.reserve(state.id, role, maximum, request_hash)
            self.store.event(
                state.id,
                "agent_started",
                state.stage,
                {
                    "call_id": call_id,
                    "role": role,
                    "agent": index,
                    "model": cfg.model if self.config.mode != "demo" else "offline-fixture",
                    "prompt": request.prompt,
                    "system": request.system,
                    "split_context": request.split_context,
                    "evidence_view": evidence_view,
                    **provenance,
                    "cache_key": key,
                    "attempt": attempt,
                },
            )
            if (
                self.provider is None
                and self.config.mode != "demo"
                and role not in self.config.role_commands
            ):

                def record_progress(update: dict[str, Any], call_id: str = call_id) -> None:
                    self.store.event(
                        state.id,
                        "agent_progress",
                        state.stage,
                        {
                            **update,
                            "call_id": call_id,
                            "role": role,
                            "agent": index,
                            "model": cfg.model,
                        },
                    )

                cast(CompatibleProvider, provider).progress = record_progress
            try:
                if role in self.config.role_commands:
                    response = self._command(role, request, cfg, maximum)
                else:
                    response = provider.complete(request)
            except ProviderError as exc:
                self.store.settle(call_id, exc.usage)
                if exc.quota_exhausted_until:
                    self._record_exhaustion(state, role, cfg, exc)
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
                        "rate_limited": exc.rate_limited,
                        "retry_after_seconds": exc.retry_after_seconds,
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

    def _guard_size(
        self,
        state: RunState,
        role: str,
        index: int,
        cfg: ProviderConfig,
        request: AgentRequest,
    ) -> None:
        """Refuse a request that a model's declared token limits can never accept."""
        limits = model_limits(self.config, cfg)
        checks = (
            ("context window", limits.context_window_tokens),
            ("tokens-per-minute quota", limits.tokens_per_minute),
        )
        if not any(limit for _, limit in checks):
            return
        estimate = math.ceil(request_input_bound(request) / BYTES_PER_TOKEN)
        exceeded = [(name, limit) for name, limit in checks if limit and estimate > limit]
        if not exceeded:
            return
        self.store.event(
            state.id,
            "model_request_oversized",
            state.stage,
            {
                "role": role,
                "agent": index,
                "model": cfg.model,
                "estimated_input_tokens": estimate,
                "context_window_tokens": limits.context_window_tokens,
                "tokens_per_minute": limits.tokens_per_minute,
            },
        )
        name, limit = exceeded[0]
        raise RequestTooLarge(
            f"Request (~{estimate} input tokens) exceeds model {cfg.model}'s {name} "
            f"({limit} tokens); it was not sent",
            recoverable=True,
            model=cfg.model,
        )

    @staticmethod
    def _reservation(config: ProviderConfig, request: AgentRequest) -> float:
        tokens = request_input_bound(request)
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
