"""
LLM Routing Module.

Manages model selection and configuration for different analysis modes.
"""

from typing import Optional, Literal
from pydantic import BaseModel

from core.config import settings


class LLMConfig(BaseModel):
    """Configuration for an LLM call."""

    model: str
    max_input_tokens: int
    max_output_tokens: int
    temperature: float = 0.0
    top_p: float = 1.0
    response_format: Literal["json", "text"] = "json"

    # Cost tracking
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0

    # Metadata
    mode: str = "batch_score"
    prompt_version: str = "v1.0.0"


# Model configurations
MODEL_CONFIGS = {
    "gpt-4o-mini": {
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
    },
    "gpt-5-mini": {
        "cost_per_1k_input": 0.0003,
        "cost_per_1k_output": 0.0012,
    },
    "claude-3-haiku": {
        "cost_per_1k_input": 0.00025,
        "cost_per_1k_output": 0.00125,
    },
    "claude-sonnet": {
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
    },
}


class LLMRouter:
    """
    Routes LLM requests to appropriate models based on mode.

    Two modes:
    - batch_score: Cheap, fast, low output tokens (< $0.01/event)
    - full_audit: More expensive, detailed output (for high-score candidates)
    """

    def __init__(
        self,
        batch_score_model: Optional[str] = None,
        full_audit_model: Optional[str] = None,
    ):
        """
        Initialize the router.

        Args:
            batch_score_model: Model for batch scoring
            full_audit_model: Model for full audit
        """
        self.batch_score_model = batch_score_model or settings.llm_batch_score_model
        self.full_audit_model = full_audit_model or settings.llm_full_audit_model

    def get_config(
        self,
        mode: Literal["batch_score", "full_audit"],
        prompt_version: str = "v1.0.0",
    ) -> LLMConfig:
        """
        Get LLM configuration for a specific mode.

        Args:
            mode: Analysis mode
            prompt_version: Version of the prompt to use

        Returns:
            LLMConfig for the mode
        """
        if mode == "batch_score":
            model = self.batch_score_model
            model_info = MODEL_CONFIGS.get(model, {})

            return LLMConfig(
                model=model,
                max_input_tokens=3000,
                max_output_tokens=500,
                temperature=0.0,
                response_format="json",
                cost_per_1k_input=model_info.get("cost_per_1k_input", 0),
                cost_per_1k_output=model_info.get("cost_per_1k_output", 0),
                mode="batch_score",
                prompt_version=prompt_version,
            )

        elif mode == "full_audit":
            model = self.full_audit_model
            model_info = MODEL_CONFIGS.get(model, {})

            return LLMConfig(
                model=model,
                max_input_tokens=8000,
                max_output_tokens=2000,
                temperature=0.0,
                response_format="json",
                cost_per_1k_input=model_info.get("cost_per_1k_input", 0),
                cost_per_1k_output=model_info.get("cost_per_1k_output", 0),
                mode="full_audit",
                prompt_version=prompt_version,
            )

        else:
            raise ValueError(f"Unknown mode: {mode}")

    def calculate_cost(
        self, config: LLMConfig, input_tokens: int, output_tokens: int
    ) -> float:
        """
        Calculate cost for an LLM call.

        Args:
            config: LLM configuration
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        input_cost = (input_tokens / 1000) * config.cost_per_1k_input
        output_cost = (output_tokens / 1000) * config.cost_per_1k_output
        return input_cost + output_cost

    def should_trigger_full_audit(
        self,
        score: float,
        is_ui_request: bool = False,
        threshold_low: float = 0.65,
        threshold_high: float = 0.85,
    ) -> bool:
        """
        Determine if full_audit should be triggered.

        Args:
            score: Score from batch_score
            is_ui_request: Whether this is a UI request
            threshold_low: Lower threshold for borderline cases
            threshold_high: Upper threshold for high confidence

        Returns:
            True if full_audit should be triggered
        """
        # UI requests always get full audit
        if is_ui_request:
            return True

        # High score candidates
        if score >= threshold_high:
            return True

        # Borderline cases (for additional validation)
        if threshold_low <= score < threshold_high:
            return True

        return False


# Global router instance
_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Get the global LLM router."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
