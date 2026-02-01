"""
Cost Optimizer for LLM Analysis.

Ensures cost per event stays under budget ($0.01/event target).

Strategies:
1. Token budget control in transcript pack
2. Smart model routing (cheap first, expensive only if needed)
3. Caching for repeated queries
4. Batch processing for efficiency
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import hashlib


class CostMetrics(BaseModel):
    """Cost tracking metrics for a single analysis."""

    event_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str


class CostBudget(BaseModel):
    """Cost budget configuration."""

    max_cost_per_event: float = 0.01  # $0.01 target
    warning_threshold: float = 0.008  # Warn at 80% of budget
    hard_limit: float = 0.015  # Absolute maximum


class ModelPricing(BaseModel):
    """Pricing information for a model."""

    model_id: str
    input_cost_per_1k: float  # $ per 1000 input tokens
    output_cost_per_1k: float  # $ per 1000 output tokens
    max_output_tokens: int


# Current model pricing (as of 2026-01)
MODEL_PRICING: Dict[str, ModelPricing] = {
    # Cheap models for batch_score
    "gpt-4o-mini": ModelPricing(
        model_id="gpt-4o-mini",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0006,
        max_output_tokens=500,
    ),
    "claude-3-haiku": ModelPricing(
        model_id="claude-3-haiku",
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
        max_output_tokens=500,
    ),
    "gemini-1.5-flash": ModelPricing(
        model_id="gemini-1.5-flash",
        input_cost_per_1k=0.000075,
        output_cost_per_1k=0.0003,
        max_output_tokens=500,
    ),
    # Expensive models for full_audit
    "gpt-4o": ModelPricing(
        model_id="gpt-4o",
        input_cost_per_1k=0.0025,
        output_cost_per_1k=0.01,
        max_output_tokens=2000,
    ),
    "claude-3.5-sonnet": ModelPricing(
        model_id="claude-3.5-sonnet",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        max_output_tokens=2000,
    ),
}


class CostOptimizer:
    """
    Optimizes LLM costs while maintaining quality.

    Strategy:
    1. Use cheap models for batch_score
    2. Control input tokens via transcript pack size
    3. Limit output tokens via structured JSON
    4. Cache results for repeated queries
    """

    def __init__(
        self,
        budget: Optional[CostBudget] = None,
        enable_caching: bool = True,
    ):
        """
        Initialize optimizer.

        Args:
            budget: Cost budget configuration
            enable_caching: Whether to enable result caching
        """
        self.budget = budget or CostBudget()
        self.enable_caching = enable_caching
        self._cache: Dict[str, Any] = {}
        self._cost_history: List[CostMetrics] = []

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: Optional[int] = None,
    ) -> float:
        """
        Estimate cost for a query.

        Args:
            model: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens (uses max if not specified)

        Returns:
            Estimated cost in USD
        """
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            raise ValueError(f"Unknown model: {model}")

        if output_tokens is None:
            output_tokens = pricing.max_output_tokens

        input_cost = (input_tokens / 1000) * pricing.input_cost_per_1k
        output_cost = (output_tokens / 1000) * pricing.output_cost_per_1k

        return input_cost + output_cost

    def check_budget(
        self,
        model: str,
        input_tokens: int,
    ) -> Dict[str, Any]:
        """
        Check if query is within budget.

        Args:
            model: Model identifier
            input_tokens: Number of input tokens

        Returns:
            Dict with budget check results
        """
        estimated = self.estimate_cost(model, input_tokens)

        return {
            "estimated_cost": estimated,
            "within_budget": estimated <= self.budget.max_cost_per_event,
            "within_warning": estimated <= self.budget.warning_threshold,
            "exceeds_hard_limit": estimated > self.budget.hard_limit,
            "budget_remaining": self.budget.max_cost_per_event - estimated,
        }

    def select_optimal_model(
        self,
        mode: str,
        input_tokens: int,
    ) -> str:
        """
        Select optimal model for budget.

        Args:
            mode: Analysis mode ("batch_score" or "full_audit")
            input_tokens: Number of input tokens

        Returns:
            Recommended model identifier
        """
        if mode == "batch_score":
            # Try cheap models in order of preference
            for model in ["gemini-1.5-flash", "gpt-4o-mini", "claude-3-haiku"]:
                check = self.check_budget(model, input_tokens)
                if check["within_budget"]:
                    return model

            # Fall back to cheapest even if over budget
            return "gemini-1.5-flash"

        else:  # full_audit
            # Use quality models, prefer cheaper if within budget
            for model in ["claude-3.5-sonnet", "gpt-4o"]:
                check = self.check_budget(model, input_tokens)
                if not check["exceeds_hard_limit"]:
                    return model

            return "gpt-4o"

    def calculate_max_input_tokens(
        self,
        model: str,
        target_cost: Optional[float] = None,
    ) -> int:
        """
        Calculate maximum input tokens for budget.

        Args:
            model: Model identifier
            target_cost: Target cost (uses budget if not specified)

        Returns:
            Maximum input tokens
        """
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            raise ValueError(f"Unknown model: {model}")

        if target_cost is None:
            target_cost = self.budget.max_cost_per_event

        # Reserve cost for output
        output_cost = (pricing.max_output_tokens / 1000) * pricing.output_cost_per_1k
        available_for_input = target_cost - output_cost

        if available_for_input <= 0:
            return 0

        max_tokens = int((available_for_input / pricing.input_cost_per_1k) * 1000)
        return max_tokens

    def get_cache_key(
        self,
        event_id: str,
        model: str,
        prompt_hash: str,
    ) -> str:
        """Generate cache key for a query."""
        key_data = f"{event_id}:{model}:{prompt_hash}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def get_cached_result(
        self,
        event_id: str,
        model: str,
        prompt_hash: str,
    ) -> Optional[Any]:
        """Get cached result if available."""
        if not self.enable_caching:
            return None

        key = self.get_cache_key(event_id, model, prompt_hash)
        return self._cache.get(key)

    def cache_result(
        self,
        event_id: str,
        model: str,
        prompt_hash: str,
        result: Any,
    ) -> None:
        """Cache a result."""
        if not self.enable_caching:
            return

        key = self.get_cache_key(event_id, model, prompt_hash)
        self._cache[key] = result

    def record_cost(
        self,
        event_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> CostMetrics:
        """
        Record actual cost for tracking.

        Args:
            event_id: Event identifier
            model: Model used
            input_tokens: Actual input tokens
            output_tokens: Actual output tokens

        Returns:
            CostMetrics record
        """
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            cost = 0.0
        else:
            cost = (
                (input_tokens / 1000) * pricing.input_cost_per_1k
                + (output_tokens / 1000) * pricing.output_cost_per_1k
            )

        metrics = CostMetrics(
            event_id=event_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            timestamp=datetime.utcnow().isoformat(),
        )

        self._cost_history.append(metrics)
        return metrics

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get summary of costs."""
        if not self._cost_history:
            return {
                "total_events": 0,
                "total_cost": 0.0,
                "avg_cost": 0.0,
                "over_budget_count": 0,
            }

        total_cost = sum(m.cost_usd for m in self._cost_history)
        avg_cost = total_cost / len(self._cost_history)
        over_budget = sum(
            1 for m in self._cost_history
            if m.cost_usd > self.budget.max_cost_per_event
        )

        return {
            "total_events": len(self._cost_history),
            "total_cost": total_cost,
            "avg_cost": avg_cost,
            "over_budget_count": over_budget,
            "over_budget_pct": over_budget / len(self._cost_history) * 100,
        }


# Token budget recommendations for transcript pack
TOKEN_BUDGETS = {
    "gemini-1.5-flash": 8000,  # Very cheap, can use more
    "gpt-4o-mini": 4000,  # Moderate
    "claude-3-haiku": 3000,  # Slightly more expensive
    "gpt-4o": 2000,  # Expensive
    "claude-3.5-sonnet": 2000,  # Expensive
}


def get_token_budget(model: str) -> int:
    """Get recommended token budget for model."""
    return TOKEN_BUDGETS.get(model, 3000)


# Global optimizer
_optimizer: Optional[CostOptimizer] = None


def get_cost_optimizer() -> CostOptimizer:
    """Get the global cost optimizer."""
    global _optimizer
    if _optimizer is None:
        _optimizer = CostOptimizer()
    return _optimizer
