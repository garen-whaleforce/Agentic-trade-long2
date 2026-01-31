"""
Parameter Grid for Constrained Optimization.

Defines the limited parameter space for tuning.

IMPORTANT: Keep parameter space small to prevent overfitting.
Maximum recommended degrees of freedom: 4-6
"""

from typing import List, Dict, Any, Iterator
from itertools import product
from pydantic import BaseModel


class ParameterGrid(BaseModel):
    """
    Constrained parameter grid.

    Only allowed parameters:
    - score_threshold: [0.65, 0.70, 0.75, 0.80]
    - evidence_min_count: [2, 3]
    - block_on_margin_concern: [True, False]
    - universe_filter: [None, "large_cap", "sp500"]
    """

    score_thresholds: List[float] = [0.65, 0.70, 0.75, 0.80]
    evidence_min_counts: List[int] = [2, 3]
    block_on_margin_concern: List[bool] = [True, False]
    universe_filters: List[str] = ["none", "large_cap"]

    def total_combinations(self) -> int:
        """Get total number of parameter combinations."""
        return (
            len(self.score_thresholds)
            * len(self.evidence_min_counts)
            * len(self.block_on_margin_concern)
            * len(self.universe_filters)
        )

    def validate_degrees_of_freedom(self, max_dof: int = 6) -> bool:
        """
        Validate that degrees of freedom is within limit.

        Args:
            max_dof: Maximum allowed degrees of freedom

        Returns:
            True if within limit
        """
        dof = (
            len(self.score_thresholds)
            + len(self.evidence_min_counts)
            + len(self.block_on_margin_concern)
            + len(self.universe_filters)
            - 4  # Subtract 4 for the 4 parameter types
        )
        return dof <= max_dof

    def iter_configs(self) -> Iterator[Dict[str, Any]]:
        """
        Iterate over all parameter configurations.

        Yields:
            Dictionary with parameter values
        """
        for combo in product(
            self.score_thresholds,
            self.evidence_min_counts,
            self.block_on_margin_concern,
            self.universe_filters,
        ):
            yield {
                "score_threshold": combo[0],
                "evidence_min_count": combo[1],
                "block_on_margin_concern": combo[2],
                "universe_filter": combo[3] if combo[3] != "none" else None,
            }

    def get_config_id(self, config: Dict[str, Any]) -> str:
        """
        Generate a unique ID for a config.

        Args:
            config: Parameter configuration

        Returns:
            Unique identifier string
        """
        parts = [
            f"s{config['score_threshold']}",
            f"e{config['evidence_min_count']}",
            f"m{1 if config['block_on_margin_concern'] else 0}",
            f"u{config['universe_filter'] or 'all'}",
        ]
        return "_".join(parts)


class GridSearchResult(BaseModel):
    """Result from a single grid search configuration."""

    config_id: str
    config: Dict[str, Any]
    tune_performance: Dict[str, float]
    validate_performance: Optional[Dict[str, float]] = None
    is_valid: bool = True
    validation_notes: Optional[str] = None


class GridSearchSummary(BaseModel):
    """Summary of grid search results."""

    total_configs: int
    valid_configs: int
    best_tune_configs: List[GridSearchResult]
    best_validate_configs: List[GridSearchResult]


class GridSearchRunner:
    """
    Runs constrained grid search.

    Process:
    1. Run all configs on tune period
    2. Select top N by Sharpe
    3. Validate top N on validate period
    4. Select final candidate
    """

    def __init__(
        self,
        grid: ParameterGrid,
        top_n: int = 5,
    ):
        """
        Initialize the runner.

        Args:
            grid: Parameter grid
            top_n: Number of top configs to validate
        """
        self.grid = grid
        self.top_n = top_n

        # Validate grid
        if not grid.validate_degrees_of_freedom():
            raise ValueError(
                f"Parameter grid has too many degrees of freedom. "
                f"Total combinations: {grid.total_combinations()}"
            )

    def select_top_configs(
        self,
        results: List[GridSearchResult],
        metric: str = "sharpe_ratio",
    ) -> List[GridSearchResult]:
        """
        Select top N configs by metric.

        Args:
            results: List of grid search results
            metric: Metric to sort by

        Returns:
            Top N configurations
        """
        # Filter valid configs
        valid = [r for r in results if r.is_valid]

        # Sort by metric (descending)
        sorted_results = sorted(
            valid,
            key=lambda r: r.tune_performance.get(metric, 0),
            reverse=True,
        )

        return sorted_results[: self.top_n]

    def generate_summary(
        self,
        tune_results: List[GridSearchResult],
        validate_results: List[GridSearchResult],
    ) -> GridSearchSummary:
        """
        Generate grid search summary.

        Args:
            tune_results: Results from tune period
            validate_results: Results from validate period

        Returns:
            GridSearchSummary
        """
        return GridSearchSummary(
            total_configs=len(tune_results),
            valid_configs=len([r for r in tune_results if r.is_valid]),
            best_tune_configs=self.select_top_configs(tune_results),
            best_validate_configs=self.select_top_configs(
                validate_results, metric="sharpe_ratio"
            ),
        )


# Default grid
DEFAULT_GRID = ParameterGrid()
