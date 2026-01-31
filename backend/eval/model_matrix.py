"""
Model Matrix Configuration.

Defines candidate models for evaluation.
"""

from typing import List, Optional
from pydantic import BaseModel


class ModelConfig(BaseModel):
    """Configuration for a single model."""

    id: str
    provider: str
    cost_per_1k_input: float
    cost_per_1k_output: float
    max_tokens: int = 4096
    supports_json: bool = True


class ModelMatrix(BaseModel):
    """
    Matrix of models for evaluation.

    Separate models for batch_score (cheap) and full_audit (better).
    """

    batch_score_models: List[ModelConfig]
    full_audit_models: List[ModelConfig]
    prompt_versions: List[str]


# Default model matrix
DEFAULT_MODEL_MATRIX = ModelMatrix(
    batch_score_models=[
        ModelConfig(
            id="gpt-4o-mini",
            provider="openai",
            cost_per_1k_input=0.00015,
            cost_per_1k_output=0.0006,
        ),
        ModelConfig(
            id="claude-3-haiku",
            provider="anthropic",
            cost_per_1k_input=0.00025,
            cost_per_1k_output=0.00125,
        ),
    ],
    full_audit_models=[
        ModelConfig(
            id="gpt-5-mini",
            provider="openai",
            cost_per_1k_input=0.0003,
            cost_per_1k_output=0.0012,
        ),
        ModelConfig(
            id="claude-sonnet",
            provider="anthropic",
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
        ),
    ],
    prompt_versions=["v1.0.0", "v1.1.0", "v1.2.0"],
)


def get_model_matrix() -> ModelMatrix:
    """Get the default model matrix."""
    return DEFAULT_MODEL_MATRIX
