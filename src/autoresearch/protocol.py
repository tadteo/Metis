"""Agent-established measurement with immutable provenance and independent inspection."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, ValidationError, model_validator

from .contracts import ExperimentSpec, Model
from .runtime_support import ExecutionError, file_identity, read_text, relative_parts, write_file

if TYPE_CHECKING:
    from .agents import AgentRunner
    from .config import ResearchConfig
    from .contracts import RunState
    from .engine import Engine


class ReferenceValue(Model):
    evidence_id: str = Field(min_length=1)
    location: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)


class ResearchProtocol(Model):
    metrics: dict[str, Literal["min", "max"]]
    sota: dict[str, float]
    reference_sources: dict[str, ReferenceValue]
    specification: str = Field(min_length=30)
    measurement_mode: Literal["separate", "instrumented"] = "separate"
    measurement_paths: list[str] = Field(default_factory=list)
    evaluator_argv: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(min_length=1)
    dataset_manifest: dict[str, str] = Field(default_factory=dict)
    metric_units: dict[
        str,
        Literal["scalar", "fraction", "percent", "percentage_points", "seconds", "milliseconds"],
    ] = Field(default_factory=dict)
    analysis_artifacts: list[str] = Field(default_factory=list)
    measurement_checks: list[list[str]] = Field(min_length=1, max_length=10)
    measurement_artifacts: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def complete(self) -> ResearchProtocol:
        if (
            not self.metrics
            or set(self.metrics) != set(self.sota)
            or set(self.metrics) != set(self.reference_sources)
        ):
            raise ValueError("Every metric needs its original full-benchmark value and source")
        if set(self.protected_paths) & set(self.measurement_artifacts):
            raise ValueError("Measurement outputs must be regenerated, not protected inputs")
        for path in self.protected_paths + self.measurement_artifacts + self.measurement_paths:
            relative_parts(path)
            if path == "metrics.json":
                raise ValueError(
                    "Measurement evidence must include underlying outputs, not only metrics.json"
                )
        if self.measurement_mode == "separate" and not any(
            argument in self.protected_paths for argument in self.evaluator_argv[1:]
        ):
            raise ValueError("Measurement must invoke a sealed source asset")
        if self.measurement_mode == "instrumented" and (
            self.evaluator_argv or not self.measurement_paths
        ):
            raise ValueError(
                "Instrumented measurement needs inspectable source paths and no separate evaluator"
            )
        if any(not command for command in self.measurement_checks):
            raise ValueError("Measurement checks must be executable argument arrays")
        if not self.dataset_manifest or not any(
            key.startswith("sha256:") for key in self.dataset_manifest
        ):
            raise ValueError("Identify actual data/split bytes before sealing measurement")
        for key in self.dataset_manifest:
            if (
                key.startswith("sha256:")
                and not key[7:].startswith("/")
                and key[7:] not in self.protected_paths
            ):
                raise ValueError(
                    "Relative dataset/split files must be protected measurement assets"
                )
        return self

    def project_fields(self) -> dict[str, Any]:
        return {
            **self.model_dump(
                exclude={
                    "reference_sources",
                    "measurement_checks",
                    "measurement_artifacts",
                    "measurement_mode",
                    "measurement_paths",
                }
            ),
            "primary_metric": next(iter(self.metrics)),
        }


class ProtocolRepair(ValueError):
    """A retained proposal needs bounded baseline-agent repair, not user command entry."""


def seal(*args: Any, **kwargs: Any) -> ResearchConfig:
    try:
        return _seal(*args, **kwargs)
    except (ValidationError, ExecutionError, FileNotFoundError) as exc:
        raise ProtocolRepair(str(exc)) from exc


def _seal(
    engine: Engine, state: RunState, config: ResearchConfig, agents: AgentRunner
) -> ResearchConfig:
    """Called within baseline coding, before any formal measurement is accepted."""
    from .execution import Executor
    from .research_inputs import resolved_config

    if state.research_protocol:
        return resolved_config(config, state, engine.store)
    if state.active_output is None:
        raise ValueError("Baseline implementation is missing")
    proposal = ResearchProtocol.model_validate(state.active_output.structured.get("protocol"))
    from .config import ProjectConfig

    fields = proposal.project_fields()
    if config.project.result_preference == "pareto":
        fields["primary_metric"] = config.project.primary_metric
    ProjectConfig.model_validate({**config.project.model_dump(), **fields})
    evidence = {item.id: item for item in state.evidence}
    import math
    import re

    for metric, citation in proposal.reference_sources.items():
        record = evidence.get(citation.evidence_id)
        if record is None or citation.excerpt not in (
            record.full_text or record.abstract or record.excerpt
        ):
            raise ProtocolRepair(
                "Reference value must quote observed source content and identify its location"
            )
        numbers = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", citation.excerpt)
        if not any(
            math.isclose(float(number), proposal.sota[metric], rel_tol=1e-10, abs_tol=1e-12)
            for number in numbers
        ):
            raise ProtocolRepair(
                "Reference number must match the cited excerpt in its published scale"
            )
    payload = proposal.model_dump_json(indent=2)
    payload_digest = hashlib.sha256(payload.encode()).hexdigest()
    digest = hashlib.sha256((payload + state.active_output.model_dump_json()).encode()).hexdigest()
    source = engine.store.run_dir(state.id) / "protocols" / digest / "source"
    marker = source.parent / "source-ready.json"
    if not marker.exists():
        if source.exists():
            import uuid

            source.rename(source.parent / ("interrupted-source-" + uuid.uuid4().hex[:12]))
        engine._snapshot(engine._source_for(state), source)
        from .acquisition import materialize

        materialize(
            engine.store.run_dir(state.id),
            source,
            state.active_output.structured.get("materialized_resources", []),
        )
        for item in state.active_output.files:
            write_file(source, item.path, item.content)
        for path in state.active_output.deleted_files:
            relative_parts(path)
            (source / path).unlink()
        write_file(source.parent, "source-ready.json", json.dumps({"ready": True}))
    # Recheck expected exported bytes on every resume; a retained failed attempt is not permission to mutate it.
    for item in state.active_output.files:
        if read_text(source, item.path, 10000000) != item.content:
            raise ValueError("Proposed measurement source changed before sealing")
    protected = {path: file_identity(source, path)["sha256"] for path in proposal.protected_paths}
    checks = []
    for index, command in enumerate(proposal.measurement_checks):
        check_id = f"protocol-{digest[:12]}-{index}"
        workspace = source.parent / f"check-{index}"
        if not workspace.exists():
            engine._snapshot(source, workspace)
        spec = ExperimentSpec(
            id=check_id,
            kind="measurement_check",
            workspace=str(workspace),
            argv=command,
            timeout_seconds=config.coding.command_timeout,
            metadata={
                "command_only": True,
                "protected_files": proposal.protected_paths,
                "dataset_manifest": proposal.dataset_manifest,
            },
        )
        result = engine._execute_pending(state, engine.executor or Executor(config.execution), spec)
        if result.status == "pending":
            from .coding import CodingPending

            raise CodingPending("Independent measurement check is pending")
        state.pending_job_id = None
        checks.append(result.model_dump(mode="json"))
        engine.store.artifact(
            state.id, "measurement_check", f"{check_id}.json", result.model_dump_json()
        )
        if result.status != "completed":
            state.feedback = (
                "Measurement implementation failed its check. Repair it using the retained receipt: "
                + result.stderr
            )
            if result.provenance.get("uncertain_execution"):
                raise ValueError("Reconcile the uncertain measurement check before retrying")
            raise ProtocolRepair(state.feedback)
    audit = agents.run(
        state,
        "experiment_integrity",
        {
            "source_dir": str(source),
            "specification": proposal.specification,
            "protocol_proposal": proposal.model_dump(),
            "measurement_checks": checks,
            "research_brief": state.research_brief,
            "audit_purpose": "Validate reference values, measurement meaning and recomputability before sealing; reject constant scores, leaked labels, changed splits and omitted benchmarks.",
        },
    )
    engine.store.artifact(
        state.id,
        "protocol_inspection",
        f"protocol-audit-{digest[:16]}-{state.version}.json",
        audit.model_dump_json(),
    )
    if audit.decision != "accept":
        state.feedback = audit.feedback or audit.summary
        raise ProtocolRepair("Measurement protocol inspection requires repair: " + state.feedback)
    path = f"protocols/{digest}/protocol.json"
    write_file(engine.store.run_dir(state.id), path, payload)
    state.research_protocol = {
        "version": state.counters.get("protocol_version", 0) + 1,
        "path": path,
        "sha256": payload_digest,
        "source_path": str(source.relative_to(engine.store.run_dir(state.id))),
        "protected_sha256": protected,
        "measurement_artifacts": proposal.measurement_artifacts,
        "measurement_mode": proposal.measurement_mode,
        "measurement_paths": proposal.measurement_paths,
        "measurement_sha256": {
            path: file_identity(source, path)["sha256"] for path in proposal.measurement_paths
        },
    }
    engine.store.artifact(state.id, "research_protocol", f"protocol-{digest}.json", payload)
    # Protected files now originate in the inspected protocol snapshot, not candidate edits.
    state.active_output.files = [
        item for item in state.active_output.files if item.path not in protected
    ]
    state.counters["protocol_version"] = state.research_protocol["version"]
    engine.store.save(state, "protocol_sealed", state.research_protocol)
    return resolved_config(config, state, engine.store)


def measurement_context(store: Any, state: RunState) -> dict[str, Any]:
    """Inspection sees the frozen yardstick alongside candidate code and actual outputs."""
    reference = state.research_protocol
    if not reference:
        return {}
    root = store.run_dir(state.id) / reference["source_path"]
    return {
        "sealed_measurement": reference,
        "measurement_reference_source": {
            path: {"identity": file_identity(root, path), "content": read_text(root, path, 200000)}
            for path in reference.get("measurement_paths", [])
        },
    }


def reproduce_measurement(
    engine: Engine, state: RunState, config: ResearchConfig, spec: ExperimentSpec, result: Any
) -> bool:
    """Shared method/measurement code requires a pristine rerun before critic eligibility."""
    import math
    from pathlib import Path

    from .execution import Executor

    identifier = f"measurement-{spec.id}"
    workspace = engine.store.run_dir(state.id) / "experiments" / identifier
    if not workspace.exists():
        engine._snapshot(Path(spec.metadata["input_snapshot"]), workspace)
    check = spec.model_copy(
        deep=True,
        update={
            "id": identifier,
            "workspace": str(workspace),
            "files": [],
            "kind": "measurement_reproduction",
        },
    )
    repeated = engine._execute_pending(state, engine.executor or Executor(config.execution), check)
    if repeated.status == "pending":
        return False
    state.pending_job_id = None
    engine.store.artifact(
        state.id, "measurement_reproduction", f"{identifier}.json", repeated.model_dump_json()
    )
    result.provenance["measurement_reproduction"] = {
        "id": identifier,
        "status": repeated.status,
        "metrics": repeated.metrics,
    }
    if (
        repeated.status != "completed"
        or set(result.metrics) != set(repeated.metrics)
        or any(
            not math.isclose(
                value,
                repeated.metrics[key],
                rel_tol=config.project.reproduction_tolerance,
                abs_tol=1e-10,
            )
            for key, value in result.metrics.items()
        )
    ):
        result.status = "failed"
        result.stderr += "\nIndependent measurement reproduction failed or disagreed."
    return True
