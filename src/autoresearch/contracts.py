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
    timeout_seconds: float = Field(default=180, gt=0)
    retries: int = Field(default=2, ge=0, le=8)
    json_mode: bool = True
    reasoning_effort: str | None = None


class Usage(Model):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
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
    backend: Literal["docker", "local", "slurm"] = "docker"
    allow_local: bool = False
    allowed_executables: list[str] = Field(default_factory=lambda: ["python", "python3"])
    docker_image: str = "python:3.11-slim"
    cpus: int = Field(default=2, ge=1)
    memory_mb: int = Field(default=4096, ge=128)
    slurm_partition: str = ""
    slurm_account: str = ""
    slurm_poll_seconds: int = Field(default=10, ge=1)
    max_log_bytes: int = Field(default=1000000, ge=1024)
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


class RunState(Model):
    id: str
    title: str
    objective: str
    stage: Stage = Stage.LIMITATIONS
    status: str = "ready"
    version: int = 0
    created_at: str = ""
    updated_at: str = ""
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
    comparison_origin: str = ""
    outcome: str = ""
    error: str = ""
