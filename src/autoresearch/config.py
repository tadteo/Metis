"""Deterministic public configuration; credentials are named references only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .coding import CodingConfig
from .contracts import ExecutionConfig, Model, ProviderConfig
from .paper_orchestra import PaperOrchestraConfig


class PipelineConfig(Model):
    limitation_rounds: int = Field(default=16, ge=1)
    seed_count: int = Field(default=8, ge=2)
    initial_candidates: int = Field(default=2, ge=1)
    evolved_per_round: int = Field(default=1, ge=1)
    exploration_per_round: int = Field(default=1, ge=1)
    experiment_rounds: int = Field(default=4, ge=1)
    successful_ideas: int = Field(default=4, ge=1)
    engineering_rounds: int = Field(default=2, ge=0)
    ablation_rounds: int = Field(default=1, ge=1)
    peer_rounds: int = Field(default=2, ge=1)
    meta_rounds: int = Field(default=1, ge=1)
    review_threshold: float = Field(default=8, ge=1, le=10)
    novelty_references: int = Field(default=12, ge=2)
    novelty_queries: int = Field(default=3, ge=1, le=3)
    generation_rounds: int = Field(default=16, ge=1)
    agents_per_role: int = Field(default=1, ge=1, le=32)
    critics: int = Field(default=2, ge=1, le=32)
    parallelism: int = Field(default=4, ge=1, le=64)
    escalation_confidence: float = Field(default=0.65, ge=0, le=1)
    writing_reflections: int = Field(default=3, ge=1)
    max_agent_repairs: int = Field(default=2, ge=0, le=10)

    @model_validator(mode="after")
    def validate_counts(self) -> PipelineConfig:
        if self.initial_candidates > self.seed_count:
            raise ValueError("initial_candidates must not exceed seed_count")
        return self


class PrivacyConfig(Model):
    # State is always private and needed for resume; this controls duplicate diagnostic traces.
    traces: Literal["full", "redacted", "metadata"] = "redacted"
    cache: bool = True
    redact_patterns: list[str] = Field(default_factory=list)


class BudgetConfig(Model):
    usd: float = Field(default=25, gt=0)
    max_calls: int = Field(default=2000, ge=1)
    max_experiments: int = Field(default=200, ge=1)
    wall_seconds: int = Field(default=604800, ge=1)


class LiteratureConfig(Model):
    min_novelty_sources: int = Field(default=3, ge=2)
    providers: list[str] = Field(default_factory=lambda: ["semantic_scholar", "arxiv", "crossref"])
    results_per_provider: int = Field(default=12, ge=1, le=100)
    max_results: int = Field(default=40, ge=2, le=500)
    publication_cutoff: str = ""
    timeout_seconds: float = Field(default=30, gt=0)
    full_text: bool = True
    max_full_text_chars: int = Field(default=80000, ge=1000)
    max_full_text_papers: int = Field(default=8, ge=0)
    semantic_scholar_api_key_env: str = "SEMANTIC_SCHOLAR_API_KEY"


class ScholarPeerConfig(Model):
    venue: str = "ICLR"
    publication_cutoff: str = ""
    literature_rounds: int = Field(default=3, ge=1)
    qa_pairs_per_criterion: int = Field(default=5, ge=1)
    max_search_queries: int = Field(default=12, ge=1)


class IntegrityConfig(Model):
    rerun_supplementary: bool = True
    require_claim_ledger: bool = True
    citation_repair_rounds: int = Field(default=2, ge=0)


class LayaConfig(Model):
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8000"
    api_key_env: str = "LAYA_API_KEY"
    model: str = "multilingual"
    max_len: int = Field(default=8192, ge=128, le=8192)
    timeout_seconds: float = Field(default=30, gt=0)
    cost_per_call_usd: float = Field(default=0, ge=0)
    # Advisory triage never replaces evidence-grounded scientific adjudication.
    max_input_chars: int = Field(default=6000, ge=256, le=24000)


def _default_metrics() -> dict[str, Literal["max", "min"]]:
    return {"score": "max"}


class ProjectConfig(Model):
    source_dir: str = ""
    dataset_manifest: dict[str, str] = Field(default_factory=dict)
    include: list[str] = Field(default_factory=lambda: ["*", "**/*"])
    baseline_argv: list[str] = Field(default_factory=list)
    metrics: dict[str, Literal["max", "min"]] = Field(default_factory=_default_metrics)
    # Operator-owned units and declared structured analysis outputs.
    metric_units: dict[
        str,
        Literal["scalar", "fraction", "percent", "percentage_points", "seconds", "milliseconds"],
    ] = Field(default_factory=dict)
    analysis_artifacts: list[str] = Field(default_factory=list)
    # Original published full-benchmark values; never substitute subset results.
    sota: dict[str, float] = Field(default_factory=dict)
    baseline_expected: dict[str, float] = Field(default_factory=dict)
    reproduction_tolerance: float = Field(default=0.05, ge=0)
    primary_metric: str = "score"
    min_improvement: float = Field(default=0, ge=0)
    result_preference: Literal["scientific_critic", "pareto"] = "scientific_critic"
    experiment_timeout: int = Field(default=3600, ge=1, le=604800)
    specification: str = ""
    seeds: list[int] = Field(default_factory=lambda: [0])
    # Evaluator executes after proposed training command. Keep evaluator outside agent edits.
    evaluator_argv: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_metrics(self) -> ProjectConfig:
        import math

        if set(self.metric_units) - set(self.metrics):
            raise ValueError("metric_units must name registered metrics")
        from .runtime_support import relative_parts

        for artifact in self.analysis_artifacts:
            relative_parts(artifact)
            if artifact == "metrics.json":
                raise ValueError("analysis artifacts must not overwrite metrics.json")
        if len(set(self.analysis_artifacts)) != len(self.analysis_artifacts):
            raise ValueError("analysis artifact paths must be unique")
        if self.primary_metric not in self.metrics:
            raise ValueError("primary_metric must be in metrics")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be nonempty and unique")
        if not all(
            math.isfinite(v) for v in [*self.sota.values(), *self.baseline_expected.values()]
        ):
            raise ValueError("baseline values must be finite")
        return self


class ResearchConfig(Model):
    # Explicit adapter for imported configurations. New inquiry surfaces select agent entry.
    entry_mode: Literal["configured", "agent"] = "configured"
    schema_version: int = 1
    mode: Literal["live", "demo"] = "live"
    # Optional complete, trusted specification bundle; never Python import instructions.
    specification_dir: str = ""
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    cheap_provider: ProviderConfig | None = None
    frontier_provider: ProviderConfig | None = None
    role_providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    role_panels: dict[str, list[ProviderConfig]] = Field(default_factory=dict)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    coding: CodingConfig = Field(default_factory=CodingConfig)
    paper_orchestra: PaperOrchestraConfig = Field(default_factory=PaperOrchestraConfig)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    literature: LiteratureConfig = Field(default_factory=LiteratureConfig)
    scholarpeer: ScholarPeerConfig = Field(default_factory=ScholarPeerConfig)
    integrity: IntegrityConfig = Field(default_factory=IntegrityConfig)
    laya: LayaConfig = Field(default_factory=LayaConfig)
    heldout_provider: ProviderConfig | None = None
    # Optional public source corpus; independent retrieval is required for verification.
    references: list[dict[str, str]] = Field(default_factory=list)
    search_enabled: bool = True
    search_endpoint: str = "https://api.crossref.org/works"
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    # Role adapters are user-configured argv, never model-selected commands.
    role_commands: dict[str, list[str]] = Field(default_factory=dict)
    # Trusted adapters must enforce this explicit ceiling across their internal calls.
    role_command_max_cost_usd: dict[str, Annotated[float, Field(ge=0, allow_inf_nan=False)]] = (
        Field(default_factory=dict)
    )

    @model_validator(mode="after")
    def validate_version(self) -> ResearchConfig:
        if self.schema_version != 1:
            raise ValueError("unsupported configuration schema_version")
        if set(self.role_commands) - set(self.role_command_max_cost_usd):
            raise ValueError(
                "every role command requires an explicit role_command_max_cost_usd cap"
            )
        if (
            self.scholarpeer.venue.lower().startswith("neurips")
            and self.pipeline.review_threshold > 6
        ):
            raise ValueError(
                "NeurIPS uses a native 1–6 recommendation: explicitly set pipeline.review_threshold within this scale"
            )
        if any(not panel for panel in self.role_panels.values()):
            raise ValueError("role_panels entries must contain at least one provider")
        return self


def load_config(path: Path | None = None) -> ResearchConfig:
    if path is None:
        return ResearchConfig()
    return ResearchConfig.model_validate_json(path.read_text())


def save_example(path: Path, demo: bool = False) -> None:
    config = ResearchConfig(mode="demo" if demo else "live")
    # A config file is public only if its user-supplied content is public.
    with path.open("x") as handle:
        handle.write(json.dumps(config.model_dump(), indent=2) + "\n")
