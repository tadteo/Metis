"""Immutable, inspectable AI behavior provenance and explicit legacy adoption.

Resuming under changed instructions or executable code is refused. Restoring the
recorded installation/specification resumes the original run; a new configuration
belongs to a new run. Public exports contain hashes, never private prompt text.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .catalog import load_catalog
from .config import ResearchConfig
from .contracts import AgentOutput, AgentRequest, BehaviorIdentity, RunState
from .legacy import assert_no_pending_work
from .runtime_support import content_digest as digest
from .store import Store
from .workflow import get_workflow


def runtime_manifest() -> dict[str, str]:
    root = Path(__file__).parent
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix in {".py", ".json", ".md", ".txt"}
        and "__pycache__" not in path.parts
        and "specs" not in path.relative_to(root).parts
    }


def describe(config: ResearchConfig) -> dict[str, Any]:
    """Resolve everything locally. This function performs no model or tool calls."""
    from .routing import resolve_route

    catalog = load_catalog(Path(config.specification_dir) if config.specification_dir else None)
    workflow = get_workflow()
    from .research_stages import HANDLERS

    workflow.validate_handlers(set(HANDLERS))
    for node in workflow.nodes.values():
        for role in node.agents:
            catalog.definition(role)
    configured = set(config.role_panels) | set(config.role_commands) | set(config.prompt_overrides)
    unknown = configured - set(catalog.agents)
    unknown |= set(config.role_providers) - set(catalog.agents) - set(catalog.models.upstream_slots)
    if unknown:
        raise ValueError("unknown configured agent roles: " + ", ".join(sorted(unknown)))
    agents = {}
    for role, definition in catalog.agents.items():
        route = resolve_route(config, role, catalog=catalog)
        agents[role] = {
            **definition.model_dump(mode="json"),
            "resolved_model": "offline-fixture" if config.mode == "demo" else route.provider.model,
            "resolved_provider": "demo" if config.mode == "demo" else route.provider.name,
            "configured_model": route.provider.model,
            "routing_reason": route.reason,
            "prompt_sha256": hashlib.sha256(
                catalog.render(role, config.prompt_overrides.get(role, "")).encode()
            ).hexdigest(),
        }
    from .paper_orchestra import resolve_writer_config

    writer = resolve_writer_config(config)
    writer_models = {}
    for key, model in writer.items():
        if key.endswith("_model_name"):
            provider = writer["compatible_models"].get(model)
            writer_models[key.removesuffix("_model_name")] = {
                "model": provider["model"] if provider else model,
                "provider": provider["name"] if provider else "native_upstream",
                "alias": model,
            }
    for role, agent_info in agents.items():
        if agent_info["handler"] == "typed_decision" and (
            config.mode == "demo" or not config.laya.enabled
        ):
            agent_info["resolved_model"] = "disabled"
            agent_info["resolved_provider"] = "none"
            agent_info["routing_reason"] = "typed_advisory_disabled"
        elif role in config.role_commands and config.mode == "live":
            agent_info["resolved_model"] = "adapter_reported"
            agent_info["resolved_provider"] = "external_command"
            agent_info["routing_reason"] = "role_command"
        elif agent_info["handler"] == "writer" and config.mode == "live":
            agent_info["resolved_model"] = writer_models["writer"]["model"]
            agent_info["resolved_provider"] = writer_models["writer"]["provider"]
            agent_info["routing_reason"] = "official_writer_workflow"
            agent_info["upstream_models"] = writer_models
    return {
        "catalog": catalog.manifest(),
        "catalog_sha256": catalog.digest,
        "agents": agents,
        "workflow": workflow.manifest(),
        "workflow_sha256": workflow.digest,
    }


def extension_manifest(extensions: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    """Pin injected code and stable configuration, never mutable observations.

    Live custom adapters must implement behavior_identity() returning JSON data.
    Built-in configured adapters use their validated Pydantic configuration.
    Demo-only source identities are explicitly weaker and cannot be used live.
    """
    result = {}
    for name, implementation in extensions.items():
        if implementation is None:
            continue
        owner = implementation.__self__ if inspect.ismethod(implementation) else implementation
        target = (
            implementation.__func__
            if inspect.ismethod(implementation)
            else implementation
            if inspect.isfunction(implementation) or inspect.isclass(implementation)
            else type(implementation)
        )
        try:
            source_hash = hashlib.sha256(inspect.getsource(target).encode()).hexdigest()
        except (OSError, TypeError):
            source_hash = "unavailable"
        explicit = getattr(owner, "behavior_identity", None)
        config = getattr(owner, "config", None)
        if callable(explicit):
            configuration = explicit()
            scope = "explicit_adapter_identity"
        elif target.__module__.startswith("autoresearch.") and isinstance(config, BaseModel):
            configuration = config.model_dump(mode="json")
            if getattr(implementation, "_client", None) is not None and strict:
                raise ValueError(f"{name}: injected transport requires behavior_identity()")
            scope = "builtin_configuration"
        elif strict:
            raise ValueError(
                f"{name}: live extensions require behavior_identity() with stable configuration"
            )
        else:
            configuration = None
            scope = "demo_source_only"
        # Validate JSON now; do not serialize arbitrary objects or credentials by repr.
        json.dumps(configuration, allow_nan=False)
        result[name] = {
            "implementation": f"{target.__module__}.{target.__qualname__}",
            "source_sha256": source_hash,
            "configuration": configuration,
            "scope": scope,
        }
    return result


def external_adapter_manifest(config: ResearchConfig) -> dict[str, Any]:
    """Pin configured command entrypoints without launching external processes.

    Interpreter scripts must have absolute paths because workers run in private
    directories. Dependencies beyond entrypoints belong in the adapter's declared
    deployment (for example a locked environment); hashes do not claim that closure.
    """
    result = {}
    for role, argv in config.role_commands.items():
        if not argv:
            raise ValueError(f"{role}: empty adapter command")
        executable = shutil.which(argv[0])
        if executable is None:
            raise ValueError(f"{role}: adapter executable is unavailable")
        paths = [Path(executable).resolve(strict=True)]
        if paths[0].name.startswith("python") and "-m" in argv[1:]:
            raise ValueError(
                f"{role}: use an absolute adapter script instead of an unpinned -m module"
            )
        for argument in argv[1:]:
            candidate = Path(argument)
            if candidate.is_absolute() and candidate.is_file():
                paths.append(candidate.resolve(strict=True))
            elif candidate.suffix.lower() in {".py", ".js", ".mjs", ".sh", ".rb", ".pl"}:
                if not candidate.is_absolute():
                    raise ValueError(f"{role}: adapter script paths must be absolute")
                paths.append(candidate.resolve(strict=True))
        sources = {}
        for path in paths:
            with path.open("rb") as stream:
                sources[str(path)] = hashlib.file_digest(stream, "sha256").hexdigest()
        result[role] = {"argv": argv, "entrypoint_sha256": sources}
    return result


def snapshot(config: ResearchConfig, *, extensions: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = describe(config)
    catalog = load_catalog(Path(config.specification_dir) if config.specification_dir else None)
    runtime = runtime_manifest()
    return {
        "format_version": 1,
        "extensions": extensions or {},
        "external_adapters": external_adapter_manifest(config),
        "catalog_files": catalog.snapshot(),
        **resolved,
        "prompts": {
            role: catalog.render(role, config.prompt_overrides.get(role, ""))
            for role in catalog.agents
        },
        "schemas": {
            "AgentRequest": AgentRequest.model_json_schema(),
            "AgentOutput": AgentOutput.model_json_schema(),
            "RunState": RunState.model_json_schema(),
        },
        "configuration": config.model_dump(mode="json", exclude={"budget"}),
        "runtime": runtime,
        "runtime_sha256": digest(runtime),
        "provenance_scope": "Local definitions, resolved instructions, configuration, schemas and executable source. Upstream writer source is independently pinned and verified by its adapter; actual calls record actual model/usage. Budget changes have their own journal.",
    }


def identity(bundle: dict[str, Any], *, legacy_adoption: bool = False) -> BehaviorIdentity:
    return BehaviorIdentity(
        bundle_sha256=digest(bundle),
        catalog_sha256=bundle["catalog_sha256"],
        workflow_sha256=bundle["workflow_sha256"],
        runtime_sha256=bundle["runtime_sha256"],
        legacy_adoption=legacy_adoption,
    )


def archive(store: Store, state: RunState, bundle: dict[str, Any]) -> None:
    record = store.artifact(
        state.id, "ai_behavior", "ai-behavior.json", json.dumps(bundle, sort_keys=True, indent=2)
    )
    store.event(
        state.id,
        "behavior_pinned",
        state.stage,
        {
            "identity": state.behavior.model_dump() if state.behavior else None,
            "artifact_id": record["id"],
        },
    )


def recorded(store: Store, state: RunState) -> dict[str, Any]:
    if state.behavior is None:
        raise ValueError(
            "legacy run has no AI behavior bundle; inspect it and explicitly use adopt-behavior before continuing"
        )
    records = [a for a in store.artifacts(state.id) if a["kind"] == "ai_behavior"]
    if len(records) != 1:
        raise ValueError("AI behavior bundle is missing or ambiguous")
    bundle: dict[str, Any] = json.loads(store.artifact_content(state.id, records[0]["id"]))
    if digest(bundle) != state.behavior.bundle_sha256:
        raise ValueError("AI behavior bundle does not match the checkpoint identity")
    return bundle


def verify(
    store: Store,
    state: RunState,
    config: ResearchConfig,
    *,
    extensions: dict[str, Any] | None = None,
) -> None:
    recorded(store, state)
    current = snapshot(config, extensions=extensions)
    if state.behavior is None or digest(current) != state.behavior.bundle_sha256:
        raise ValueError(
            "AI behavior changed since this run was created. Restore its recorded source/specification/configuration to resume, or create a new run. Inspect the ai_behavior artifact for exact provenance."
        )


def adopt_legacy(store: Store, run_id: str) -> RunState:
    """Operator-requested migration. Never claim to recover unknown original prompts."""
    with store.lease(run_id):
        state = store.get_run(run_id)
        if state.behavior is not None:
            raise ValueError(
                "run already has pinned behavior; restore that behavior or create a new run"
            )
        assert_no_pending_work(store, run_id)
        bundle = snapshot(store.get_config(run_id))
        state.behavior = identity(bundle, legacy_adoption=True)
        archive(store, state, bundle)
        state.memory.append(
            {
                "kind": "behavior_adoption",
                "original_provenance": "unavailable",
                "bundle_sha256": state.behavior.bundle_sha256,
            }
        )
        store.save(
            state,
            "legacy_behavior_adopted",
            {"original_provenance": "unavailable", "identity": state.behavior.model_dump()},
        )
        return state


def inspect_run(store: Store, state: RunState) -> dict[str, Any]:
    """Inspect archived definitions even when the installed bundle has changed."""
    if state.behavior is None:
        return {"identity": None, "status": "legacy_unpinned", "agents": {}, "workflow": {}}
    bundle = recorded(store, state)
    return {
        "identity": state.behavior.model_dump(),
        "status": "pinned",
        "agents": bundle["agents"],
        "workflow": bundle["workflow"],
        "prompts": bundle["prompts"],
        "catalog": bundle["catalog"],
        "extensions": bundle["extensions"],
        "external_adapters": bundle["external_adapters"],
        "provenance_scope": bundle["provenance_scope"],
    }
