"""First-class Laya typed-decision transport; advisory triage, never invented prose.

Official API: https://github.com/NandhaKishorM/laya (POST /v1/systemone).
The released model is non-generative and cannot replace a scientific writing/coding role.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .catalog import AgentCatalog, TypedDecisionResult, load_catalog
from .config import LayaConfig
from .contracts import Usage
from .privacy import redact
from .providers import ProviderError, strict_json
from .routing import resolve_route
from .store import Store


def transport_payload(
    config: LayaConfig, state: dict[str, Any], questions: dict[str, Any]
) -> dict[str, Any]:
    """The exact JSON envelope shared by request provenance and the typed HTTP transport."""
    return {
        "state": state,
        "questions": questions,
        "model": config.model,
        "max_len": config.max_len,
    }


class LayaClient:
    def __init__(self, config: LayaConfig, client: httpx.Client | None = None):
        self.config, self.client = config, client
        url = urlsplit(config.base_url)
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (
                url.scheme != "https"
                and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})
            )
        ):
            raise ValueError("Laya requires HTTPS or a loopback HTTP endpoint")

    def decide(
        self, state: dict[str, Any], questions: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        config = self.config
        encoded = json.dumps(state)
        if len(encoded) > config.max_input_chars:
            raise ValueError("Laya input exceeds declared context; escalate without truncating")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(config.api_key_env, "")
        if key:
            if not key.isascii() or any(c.isspace() for c in key):
                raise ValueError("Invalid Laya credential")
            headers["Authorization"] = f"Bearer {key}"
        client = self.client or httpx.Client(trust_env=False)
        started = time.monotonic()
        try:
            response = client.post(
                config.base_url.rstrip("/") + "/v1/systemone",
                headers=headers,
                json=transport_payload(config, state, questions),
                timeout=config.timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
            result = strict_json(response.text)
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("answers"), dict)
                or not set(questions).issubset(result["answers"])
            ):
                raise ValueError("Laya did not answer the typed questions")
            TypedDecisionResult.model_validate({"answers": result["answers"]})
            raw = result.get("usage", {})
            if not isinstance(raw, dict):
                raise ValueError("Laya usage must be an object")
            usage = Usage(
                input_tokens=raw.get("input_tokens", 0),
                output_tokens=raw.get("output_tokens", 0),
                cost_usd=config.cost_per_call_usd,
                latency_seconds=time.monotonic() - started,
                estimated=not bool(raw),
            )
            return result, usage
        except (httpx.HTTPError, ValueError, TypeError):
            raise ProviderError(
                "Laya request failed or violated its typed contract; use the reasoning model",
                usage=Usage(
                    cost_usd=config.cost_per_call_usd,
                    estimated=True,
                    latency_seconds=time.monotonic() - started,
                ),
            ) from None
        finally:
            if self.client is None:
                client.close()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def triage(
    store: Store,
    run_id: str,
    role: str,
    config: LayaConfig,
    state: dict[str, Any],
    *,
    catalog: AgentCatalog | None = None,
    agent_role: str = "laya_triage",
) -> dict[str, Any]:
    """Journal an advisory typed call; its result never replaces scientific adjudication."""
    saved_config = store.get_config(run_id)
    spec_dir = getattr(saved_config, "specification_dir", "")
    catalog = catalog or load_catalog(Path(spec_dir) if spec_dir else None)
    definition = catalog.definition(agent_role)
    route = resolve_route(saved_config, agent_role, catalog=catalog)
    if config != saved_config.laya:
        raise ValueError("Laya transport must match the saved run configuration")
    questions = redact(
        catalog.questions(agent_role, saved_config.prompt_overrides.get(agent_role, "")),
        saved_config.privacy.redact_patterns,
    )
    state = redact(state, saved_config.privacy.redact_patterns)
    payload = transport_payload(config, state, questions)
    current = store.get_run(run_id)
    behavior = getattr(current, "behavior", None)
    provenance = {
        "catalog_sha256": catalog.digest,
        "agent_version": definition.version,
        "agent_sha256": hashlib.sha256(definition.model_dump_json().encode()).hexdigest(),
        "prompt_sha256": _hash(questions),
        "request_sha256": _hash(payload),
        "schema_version": definition.output_schema,
        "schema_sha256": _hash(catalog.output_schema(agent_role)),
        "route": route.reason,
        "bundle_sha256": getattr(behavior, "bundle_sha256", "unbound"),
    }
    key = _hash(
        {
            "run": run_id,
            "role": role,
            "request": payload,
            "config": config.model_dump(),
            "provenance": provenance,
        }
    )
    receipt = {
        "role": agent_role,
        "original_role": role,
        "provider": route.provider.name,
        "model": route.provider.model,
        "cache_key": key,
        **provenance,
    }
    cached = store.cache_get(key) if saved_config.privacy.cache else None
    if cached is not None:
        catalog.validate_typed_output(agent_role, cached)
        store.event(run_id, "agent_cache", current.stage, receipt)
        return cached
    call_id = store.reserve(
        run_id, agent_role, config.cost_per_call_usd, provenance["request_sha256"]
    )
    receipt["call_id"] = call_id
    store.event(
        run_id,
        "agent_started",
        current.stage,
        {**receipt, "prompt": json.dumps(payload, sort_keys=True)},
    )
    usage: Usage | None = None
    try:
        result, usage = LayaClient(config).decide(state, questions)
        catalog.validate_typed_output(agent_role, result)
    except (ProviderError, ValueError) as exc:
        # The transport records charged invalid replies; local preflight errors carry no usage.
        usage = exc.usage if isinstance(exc, ProviderError) else usage or Usage()
        store.settle(call_id, usage)
        store.event(
            run_id,
            "model_escalation",
            current.stage,
            {**receipt, "reason": str(exc), "usage": usage.model_dump()},
        )
        return {"available": False, "advisory_only": True, "escalate": True, "reason": str(exc)}
    except Exception:
        usage = Usage(cost_usd=config.cost_per_call_usd, estimated=True)
        store.settle(call_id, usage)
        store.event(
            run_id,
            "model_escalation",
            current.stage,
            {
                **receipt,
                "reason": "typed transport interrupted with uncertain usage",
                "usage": usage.model_dump(),
            },
        )
        raise
    store.settle(call_id, usage)
    result = {**result, "available": True, "advisory_only": True}
    store.event(
        run_id,
        "agent_completed",
        current.stage,
        {**receipt, "output": result, "usage": usage.model_dump()},
    )
    if saved_config.privacy.cache:
        store.cache_put(key, result)
    return result
