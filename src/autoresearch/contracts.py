"""Stable extension contracts. Unknown model fields are rejected, never executed."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, allow_inf_nan=False, hide_input_in_errors=True
    )


class Stage(StrEnum):
    INTAKE = "intake"
    LIMITATIONS = "limitations"
    VERIFY_LIMITATIONS = "verify_limitations"
    GENERATE_IDEAS = "generate_ideas"
    NOVELTY = "novelty"
    FILTER_IDEAS = "filter_ideas"
    BASELINE = "baseline"
    SUBSET = "subset"
    SUBSET_CRITIC = "subset_critic"
    SUBSET_ENGINEER = "subset_engineer"
    FULL = "full"
    FULL_CRITIC = "full_critic"
    FULL_ENGINEER = "full_engineer"
    EVOLVE = "evolve"
    SELECT = "select"
    ABLATION_PLAN = "ablation_plan"
    ABLATION = "ablation"
    ABLATION_CRITIC = "ablation_critic"
    ABLATION_REFINE = "ablation_refine"
    COMPARE = "compare"
    DRAFT = "draft"
    PEER_REVIEW = "peer_review"
    REBUTTAL_PLAN = "rebuttal_plan"
    REBUTTAL = "rebuttal"
    REVISE = "revise"
    META_REVIEW = "meta_review"
    META_REFINE = "meta_refine"
    INTEGRITY = "integrity"
    COMPLETE = "complete"


class ProviderConfig(Model):
    name: str = "xai"
    base_url: str = "https://api.x.ai/v1"
    model: str = "grok-4.7"
    api_key_env: str = "XAI_API_KEY"
    input_per_million: float = Field(default=2.0, ge=0)
    output_per_million: float = Field(default=6.0, ge=0)
    # Conservative long-context rates for budget reservation; settlement uses actual tokens.
    long_input_per_million: float = Field(default=4.0, ge=0)
    long_output_per_million: float = Field(default=12.0, ge=0)
    long_context_threshold: int = Field(default=200000, gt=0)
    max_output_tokens: int = Field(default=12000, ge=256, le=100000)
    timeout_seconds: float = Field(default=3600, gt=0)
    streaming: bool = True
    retries: int = Field(default=2, ge=0, le=8)
    json_mode: bool = True
    reasoning_effort: str | None = None
    # Request-shape fields below are omitted from serialization at their defaults, so
    # saved inventories, pinned run configurations and writer fingerprints hash as before.
    # "anthropic" selects the native Messages API adapter (``providers.AnthropicProvider``).
    adapter: Literal["openai_compatible", "anthropic"] = Field(
        default="openai_compatible", exclude_if=lambda value: value == "openai_compatible"
    )
    # Some current models reject a non-default temperature (HTTP 400); then none is sent.
    send_temperature: bool = Field(default=True, exclude_if=lambda value: value is True)
    # OpenAI reasoning models take ``max_completion_tokens``; other endpoints ``max_tokens``.
    max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = Field(
        default="max_tokens", exclude_if=lambda value: value == "max_tokens"
    )
    # Price of provider prefix-cache reads; None charges them at the full input rate.
    cached_input_per_million: float | None = Field(
        default=None, ge=0, exclude_if=lambda value: value is None
    )


class Usage(Model):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    # Provider prefix-cache reads, distinct from local complete-response reuse.
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float = Field(default=0, ge=0)
    latency_seconds: float = Field(default=0, ge=0)
    cached: bool = False
    estimated: bool = False


class AgentRequest(Model):
    run_id: str
    stage: str
    role: str
    system: str
    prompt: str
    schema_version: str = "1"
    temperature: float = Field(default=0.5, ge=0, le=2)
    cache_key: str = ""
    # Compatible transport may split the canonical JSON context into disjoint messages.
    split_context: bool = False
    provenance: dict[str, str] = Field(default_factory=dict)


class AgentResponse(Model):
    data: dict[str, Any]
    usage: Usage = Field(default_factory=Usage)
    model: str
    provider: str


class FileEdit(Model):
    path: str
    content: str


class ExperimentSpec(Model):
    id: str
    kind: str
    workspace: str
    argv: list[str] = Field(min_length=1, max_length=128)
    timeout_seconds: int = Field(default=3600, ge=1, le=604800)
    metrics_file: str = "metrics.json"
    seed: int = 0
    files: list[FileEdit] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionConfig(Model):
    # docker/podman/apptainer: containers; sandbox: OS-sandboxed native process;
    # local: unsandboxed opt-in subprocess; slurm: scheduler jobs on compute nodes.
    backend: Literal["docker", "podman", "apptainer", "sandbox", "local", "slurm"] = "docker"
    allow_local: bool = False
    allowed_executables: list[str] = Field(default_factory=lambda: ["python", "python3"])
    # OCI image reference for Docker and Podman.
    docker_image: str = "python:3.11-slim"
    # New fields are omitted while unset so existing configurations serialize unchanged.
    # Apptainer/SingularityCE image: absolute SIF path or docker://, oras://, library:// URI.
    apptainer_image: str = Field(default="", exclude_if=lambda value: value == "")
    # Python environment prefix (venv, conda or uv) for native runs: local, sandbox and
    # Slurm without a container. Its bin directory is searched before PATH.
    environment_dir: str = Field(default="", exclude_if=lambda value: value == "")
    # Runtime inside each Slurm job: the compute node's host environment or Apptainer.
    slurm_container: Literal["none", "apptainer"] = Field(
        default="none", exclude_if=lambda value: value == "none"
    )
    cpus: int = Field(default=2, ge=1)
    memory_mb: int = Field(default=4096, ge=128)
    slurm_partition: str = ""
    slurm_account: str = ""
    slurm_poll_seconds: int = Field(default=10, ge=1)
    max_log_bytes: int = Field(default=1000000, ge=1024)
    resource_hosts: list[str] = Field(
        default_factory=lambda: [
            "raw.githubusercontent.com",
            "codeload.github.com",
            "huggingface.co",
            "files.pythonhosted.org",
        ]
    )
    max_resource_bytes: int = Field(default=536870912, ge=1024, le=107374182400)
    gpus: int = Field(default=0, ge=0, le=128)
    # Explicit operator-owned datasets; Docker targets are /data/<name> only.
    readonly_mounts: dict[str, str] = Field(default_factory=dict)


class ExperimentResult(Model):
    id: str
    status: Literal["completed", "failed", "timeout", "pending", "cancelled"]
    metrics: dict[str, float] = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    job_id: str | None = None
    duration_seconds: float = 0
    provenance: dict[str, Any] = Field(default_factory=dict)


class Evidence(Model):
    id: str
    title: str
    url: str
    excerpt: str = ""
    retrieved_at: str = ""
    content_hash: str = ""
    provider: str = ""
    identifiers: dict[str, str] = Field(default_factory=dict)
    published_at: str = ""
    abstract: str = ""
    full_text: str = ""
    full_text_url: str = ""
    retrieval: dict[str, Any] = Field(default_factory=dict)


class Idea(Model):
    id: str
    title: str
    hypothesis: str
    rationale: str = ""
    parents: list[str] = Field(default_factory=list)
    novelty: float = Field(default=0, ge=0, le=10)
    status: str = "seed"
    round: int = 0
    evidence: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    workspace: str = ""


class AgentOutput(Model):
    summary: str
    decision: Literal["accept", "refine", "reject"] = "accept"
    confidence: float = Field(default=0.8, ge=0, le=1)
    feedback: str = ""
    limitations: list[str] = Field(default_factory=list)
    ideas: list[Idea] = Field(default_factory=list)
    novelty_scores: dict[str, float] = Field(default_factory=dict)
    selected_id: str | None = None
    plans: list[dict[str, Any]] = Field(default_factory=list)
    files: list[FileEdit] = Field(default_factory=list)
    argv: list[str] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=1, le=10)
    manuscript: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    return_stage: str | None = None
    # Original stage vocabulary is retained independently of the compatibility verdict.
    stage_decision: str = ""
    structured: dict[str, Any] = Field(default_factory=dict)
    deleted_files: list[str] = Field(default_factory=list)


class BehaviorIdentity(Model):
    version: Literal[1] = 1
    bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    catalog_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    workflow_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    legacy_adoption: bool = False


class ModelQuotaExhaustion(Model):
    """A model whose long-window provider quota (e.g. requests per day) is exhausted.

    Fallback routing skips the model until ``until`` (UTC ISO time); the record
    survives stages and restarts because it is part of the persisted run state.
    """

    model: str
    provider: str = ""
    until: str
    window: str = "long"
    quota_id: str = ""
    quota_value: str = ""
    quota_metric: str = ""
    recorded_at: str = ""


class RunState(Model):
    id: str
    title: str
    objective: str
    behavior: BehaviorIdentity | None = None
    stage: Stage = Stage.LIMITATIONS
    status: str = "ready"
    version: int = 0
    created_at: str = ""
    updated_at: str = ""
    research_brief: dict[str, Any] = Field(default_factory=dict)
    research_protocol: dict[str, Any] = Field(default_factory=dict)
    input_revision: int = 0
    intake_outcome: str = ""
    materials: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ideas: list[Idea] = Field(default_factory=list)
    queue: list[str] = Field(default_factory=list)
    current_idea: str | None = None
    selected_idea: str | None = None
    round: int = 0
    counters: dict[str, int] = Field(default_factory=dict)
    feedback: str = ""
    baseline: dict[str, float] = Field(default_factory=dict)
    experiments: list[ExperimentResult] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    plans: list[dict[str, Any]] = Field(default_factory=list)
    plan_index: int = 0
    manuscript: str = ""
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    memory: list[dict[str, Any]] = Field(default_factory=list)
    candidate_update: Idea | None = None
    active_output: AgentOutput | None = None
    batch_results: list[ExperimentResult] = Field(default_factory=list)
    pending_experiment: ExperimentSpec | None = None
    pending_job_id: str | None = None
    pending_job_spec_id: str = ""
    comparison_origin: str = ""
    outcome: str = ""
    error: str = ""
    # Opt-in provider quota wait: no model call before this UTC ISO time.
    quota_wait_until: str = ""
    quota_wait_attempts: int = Field(default=0, ge=0)
    quota_wait_seconds: float = Field(default=0, ge=0)
    # Long-window quota exhaustion per model identity ("base_url|model|key_env").
    # Operational routing state: excluded from model-facing views and fingerprints.
    model_quota_exhausted: dict[str, ModelQuotaExhaustion] = Field(default_factory=dict)
    # Sealed model-router refinement (artifact reference and outcome), applied as an
    # ephemeral execution view. Operational: excluded from model-facing views.
    model_plan: dict[str, Any] = Field(default_factory=dict)
