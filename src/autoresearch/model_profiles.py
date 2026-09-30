"""Opt-in routing recipes; applying one never calls a model or changes a saved run."""

from __future__ import annotations

from .config import ResearchConfig
from .contracts import ProviderConfig

# Scientific selection, coding, design, technical review and final audits retain
# the primary provider. Explicit operator overrides always take precedence.
FLASH_ROLES = (
    "limitations",
    "generate_ideas",
    "claim_extraction",
    "review_summary",
    "review_expansion",
    "review_literature",
    "review_historian",
    "review_baseline_scout",
    "review_novelty_questions",
    "writing_writer",
)


def apply_model_profile(config: ResearchConfig, name: str) -> ResearchConfig:
    """Add economical routes while preserving existing explicit routing choices."""
    if name != "google-flash":
        raise ValueError("Unknown model profile; choose google-flash")
    flash = ProviderConfig(
        name="google",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-3.8-flash",
        api_key_env="GEMINI_API_KEY",
        # Published standard rates, checked 2026-09-30; review after 2026-12-31.
        input_per_million=0.75,
        output_per_million=3.75,
        long_input_per_million=0.75,
        long_output_per_million=3.75,
        reasoning_effort="medium",
    )
    result = config.model_copy(deep=True)
    result.cheap_provider = result.cheap_provider or flash.model_copy(deep=True)
    result.frontier_provider = result.frontier_provider or result.provider.model_copy(deep=True)
    for role in FLASH_ROLES:
        if (
            role not in result.role_providers
            and role not in result.role_panels
            and role not in result.role_commands
        ):
            result.role_providers[role] = flash.model_copy(deep=True)
    return result
