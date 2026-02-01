"""
Consistency Checker.

Validates that LLM outputs are consistent across multiple runs.

Key metric: K=5 flip rate < 1%
If an event flips trade decision across K runs, it's inconsistent.
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
from statistics import mean, stdev

from pydantic import BaseModel


class ConsistencyResult(BaseModel):
    """Result of consistency check for a single event."""

    event_id: str
    k_runs: int
    decisions: List[bool]  # trade_long decisions for each run
    scores: List[float]  # scores for each run
    is_consistent: bool
    majority_decision: bool
    agreement_rate: float  # % of runs that agree with majority
    score_std: float  # Standard deviation of scores
    recommendation: str  # "TRADE", "NO_TRADE", "ABSTAIN"


class ConsistencyReport(BaseModel):
    """Overall consistency report."""

    total_events: int
    consistent_events: int
    inconsistent_events: int
    flip_rate: float  # % of events that flip
    abstain_count: int
    avg_agreement_rate: float
    avg_score_std: float
    pass_threshold: bool  # True if flip_rate < target


class ConsistencyChecker:
    """
    Checks consistency across K runs.

    If K=5 runs produce different trade decisions,
    the event is flagged as inconsistent.

    Inconsistent events should ABSTAIN (NO_TRADE)
    to avoid unreliable signals.
    """

    def __init__(
        self,
        k: int = 5,
        max_flip_rate: float = 0.01,  # 1% target
        min_agreement: float = 0.8,  # 80% agreement required
    ):
        """
        Initialize checker.

        Args:
            k: Number of runs to check
            max_flip_rate: Maximum acceptable flip rate
            min_agreement: Minimum agreement rate for consistency
        """
        self.k = k
        self.max_flip_rate = max_flip_rate
        self.min_agreement = min_agreement

    def check_event(
        self,
        event_id: str,
        run_results: List[Dict[str, Any]],
    ) -> ConsistencyResult:
        """
        Check consistency for a single event.

        Args:
            event_id: Event identifier
            run_results: List of analysis results from K runs

        Returns:
            ConsistencyResult
        """
        if len(run_results) != self.k:
            raise ValueError(
                f"Expected {self.k} runs, got {len(run_results)}"
            )

        # Extract decisions and scores
        decisions = [r.get("trade_long", r.get("trade_candidate", False)) for r in run_results]
        scores = [r.get("score", 0.0) for r in run_results]

        # Count decisions
        decision_counts = Counter(decisions)
        majority_decision = decision_counts.most_common(1)[0][0]
        majority_count = decision_counts[majority_decision]

        # Calculate metrics
        agreement_rate = majority_count / self.k
        score_std = stdev(scores) if len(scores) > 1 else 0.0

        # Determine consistency
        is_consistent = agreement_rate >= self.min_agreement

        # Determine recommendation
        if not is_consistent:
            recommendation = "ABSTAIN"
        elif majority_decision:
            recommendation = "TRADE"
        else:
            recommendation = "NO_TRADE"

        return ConsistencyResult(
            event_id=event_id,
            k_runs=self.k,
            decisions=decisions,
            scores=scores,
            is_consistent=is_consistent,
            majority_decision=majority_decision,
            agreement_rate=agreement_rate,
            score_std=score_std,
            recommendation=recommendation,
        )

    def check_batch(
        self,
        batch_results: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[List[ConsistencyResult], ConsistencyReport]:
        """
        Check consistency for a batch of events.

        Args:
            batch_results: Dict mapping event_id to list of K run results

        Returns:
            Tuple of (individual results, overall report)
        """
        results = []

        for event_id, run_results in batch_results.items():
            result = self.check_event(event_id, run_results)
            results.append(result)

        # Generate report
        total = len(results)
        consistent = sum(1 for r in results if r.is_consistent)
        inconsistent = total - consistent
        abstain = sum(1 for r in results if r.recommendation == "ABSTAIN")

        flip_rate = inconsistent / total if total > 0 else 0.0
        avg_agreement = mean(r.agreement_rate for r in results) if results else 0.0
        avg_std = mean(r.score_std for r in results) if results else 0.0

        report = ConsistencyReport(
            total_events=total,
            consistent_events=consistent,
            inconsistent_events=inconsistent,
            flip_rate=flip_rate,
            abstain_count=abstain,
            avg_agreement_rate=avg_agreement,
            avg_score_std=avg_std,
            pass_threshold=flip_rate <= self.max_flip_rate,
        )

        return results, report

    def should_trade(self, result: ConsistencyResult) -> bool:
        """
        Determine if we should trade based on consistency.

        Args:
            result: Consistency check result

        Returns:
            True if trade signal is reliable
        """
        return result.recommendation == "TRADE"


class MultiRunAnalyzer:
    """
    Runs analysis K times and aggregates results.

    This is the main entry point for consistency-checked analysis.
    """

    def __init__(
        self,
        k: int = 5,
        checker: Optional[ConsistencyChecker] = None,
    ):
        """
        Initialize analyzer.

        Args:
            k: Number of runs
            checker: Consistency checker (creates default if not provided)
        """
        self.k = k
        self.checker = checker or ConsistencyChecker(k=k)

    async def analyze_with_consistency(
        self,
        event_id: str,
        transcript_pack: str,
        analysis_fn,  # async callable that returns analysis result
    ) -> Tuple[Dict[str, Any], ConsistencyResult]:
        """
        Run analysis K times and check consistency.

        Args:
            event_id: Event identifier
            transcript_pack: Transcript content
            analysis_fn: Async function to run analysis

        Returns:
            Tuple of (final result, consistency result)
        """
        # Run K times
        run_results = []
        for i in range(self.k):
            result = await analysis_fn(event_id, transcript_pack)
            run_results.append(result)

        # Check consistency
        consistency = self.checker.check_event(event_id, run_results)

        # Build final result
        if consistency.recommendation == "ABSTAIN":
            # Return conservative result
            final = {
                "event_id": event_id,
                "score": mean(consistency.scores),
                "trade_long": False,
                "trade_candidate": False,
                "no_trade_reason": f"Inconsistent results ({consistency.agreement_rate:.0%} agreement)",
                "consistency_check": consistency.model_dump(),
            }
        else:
            # Use majority result, add consistency info
            majority_idx = consistency.decisions.index(consistency.majority_decision)
            final = run_results[majority_idx].copy()
            final["consistency_check"] = consistency.model_dump()

        return final, consistency


def check_consistency(
    event_id: str,
    run_results: List[Dict[str, Any]],
    k: int = 5,
) -> ConsistencyResult:
    """Convenience function to check consistency."""
    checker = ConsistencyChecker(k=k)
    return checker.check_event(event_id, run_results)
