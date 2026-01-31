"""
Model Evaluation Harness.

Evaluates models for:
1. Quality (JSON schema compliance, evidence compliance)
2. Consistency (K=5 flip rate)
3. Cost (per event)
4. Latency (p50, p95)

Priority: Quality = Consistency > Cost > Time
"""

import statistics
from typing import List, Dict, Any, Optional
from datetime import datetime

from pydantic import BaseModel

from .model_matrix import ModelConfig, ModelMatrix


class SingleRunResult(BaseModel):
    """Result from a single LLM run."""

    event_id: str
    run_index: int
    model: str
    prompt_version: str
    score: float
    trade_candidate: bool
    evidence_count: int
    json_valid: bool
    evidence_compliant: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class ConsistencyResult(BaseModel):
    """Result from K-run consistency test."""

    event_id: str
    model: str
    prompt_version: str
    k: int
    scores: List[float]
    trade_decisions: List[bool]
    is_consistent: bool
    score_mean: float
    score_std: float
    flip_count: int


class EvalResult(BaseModel):
    """Aggregated evaluation result for a model/prompt combination."""

    model: str
    prompt_version: str

    # Quality metrics
    json_valid_rate: float
    evidence_compliant_rate: float

    # Consistency metrics (K=5)
    flip_rate: float
    avg_score_std: float

    # Cost metrics
    avg_cost_per_event: float
    total_cost: float

    # Latency metrics
    latency_p50: float
    latency_p95: float

    # Sample sizes
    total_events: int
    consistency_test_events: int


class Scoreboard(BaseModel):
    """Evaluation scoreboard."""

    timestamp: str
    test_events: int
    k_consistency: int
    results: List[EvalResult]
    winner: Optional[str] = None
    recommendation: Optional[str] = None


class EvalHarness:
    """
    Evaluation harness for model selection.

    Runs:
    1. Basic tests (single run per event)
    2. Consistency tests (K runs per event, no cache)
    3. Aggregates results into scoreboard
    """

    def __init__(
        self,
        k_consistency: int = 5,
        consistency_sample_size: int = 50,
    ):
        """
        Initialize the harness.

        Args:
            k_consistency: Number of runs for consistency test
            consistency_sample_size: Number of events for consistency test
        """
        self.k_consistency = k_consistency
        self.consistency_sample_size = consistency_sample_size

    def evaluate_consistency(
        self,
        runs: List[SingleRunResult],
    ) -> ConsistencyResult:
        """
        Evaluate consistency from K runs.

        Args:
            runs: List of K runs for the same event

        Returns:
            ConsistencyResult
        """
        if not runs:
            raise ValueError("No runs provided")

        event_id = runs[0].event_id
        model = runs[0].model
        prompt_version = runs[0].prompt_version

        scores = [r.score for r in runs]
        decisions = [r.trade_candidate for r in runs]

        # Check consistency: all decisions must be the same
        is_consistent = len(set(decisions)) == 1

        # Count flips (number of different decisions from majority)
        majority = max(set(decisions), key=decisions.count)
        flip_count = sum(1 for d in decisions if d != majority)

        return ConsistencyResult(
            event_id=event_id,
            model=model,
            prompt_version=prompt_version,
            k=len(runs),
            scores=scores,
            trade_decisions=decisions,
            is_consistent=is_consistent,
            score_mean=statistics.mean(scores),
            score_std=statistics.stdev(scores) if len(scores) > 1 else 0,
            flip_count=flip_count,
        )

    def aggregate_results(
        self,
        basic_results: List[SingleRunResult],
        consistency_results: List[ConsistencyResult],
    ) -> EvalResult:
        """
        Aggregate results into evaluation metrics.

        Args:
            basic_results: Results from basic tests
            consistency_results: Results from consistency tests

        Returns:
            EvalResult
        """
        if not basic_results:
            raise ValueError("No basic results provided")

        model = basic_results[0].model
        prompt_version = basic_results[0].prompt_version

        # Quality metrics
        json_valid = [r for r in basic_results if r.json_valid]
        json_valid_rate = len(json_valid) / len(basic_results)

        evidence_compliant = [r for r in basic_results if r.evidence_compliant]
        evidence_compliant_rate = len(evidence_compliant) / len(basic_results)

        # Consistency metrics
        if consistency_results:
            inconsistent = [r for r in consistency_results if not r.is_consistent]
            flip_rate = len(inconsistent) / len(consistency_results)
            avg_score_std = statistics.mean(r.score_std for r in consistency_results)
        else:
            flip_rate = 0
            avg_score_std = 0

        # Cost metrics
        costs = [r.cost_usd for r in basic_results]
        avg_cost = statistics.mean(costs)
        total_cost = sum(costs)

        # Latency metrics
        latencies = sorted(r.latency_ms for r in basic_results)
        latency_p50 = latencies[len(latencies) // 2] if latencies else 0
        latency_p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

        return EvalResult(
            model=model,
            prompt_version=prompt_version,
            json_valid_rate=json_valid_rate,
            evidence_compliant_rate=evidence_compliant_rate,
            flip_rate=flip_rate,
            avg_score_std=avg_score_std,
            avg_cost_per_event=avg_cost,
            total_cost=total_cost,
            latency_p50=latency_p50,
            latency_p95=latency_p95,
            total_events=len(basic_results),
            consistency_test_events=len(consistency_results),
        )

    def generate_scoreboard(
        self,
        results: List[EvalResult],
        test_events: int,
    ) -> Scoreboard:
        """
        Generate evaluation scoreboard.

        Args:
            results: List of evaluation results
            test_events: Number of test events

        Returns:
            Scoreboard
        """
        # Sort by priority: consistency, then cost
        sorted_results = sorted(
            results,
            key=lambda r: (r.flip_rate, -r.json_valid_rate, r.avg_cost_per_event),
        )

        # Determine winner
        winner = None
        recommendation = None

        if sorted_results:
            best = sorted_results[0]

            # Check if it meets requirements
            if (
                best.json_valid_rate >= 0.99
                and best.flip_rate <= 0.01
                and best.avg_cost_per_event < 0.01
            ):
                winner = f"{best.model}_{best.prompt_version}"
                recommendation = (
                    f"Recommended: {best.model} with {best.prompt_version}. "
                    f"Flip rate: {best.flip_rate*100:.1f}%, "
                    f"Cost: ${best.avg_cost_per_event:.4f}/event"
                )
            else:
                recommendation = (
                    f"No model meets all requirements. "
                    f"Best candidate: {best.model} with {best.prompt_version}. "
                    f"Issues: "
                )
                issues = []
                if best.json_valid_rate < 0.99:
                    issues.append(f"JSON valid rate {best.json_valid_rate*100:.1f}% < 99%")
                if best.flip_rate > 0.01:
                    issues.append(f"Flip rate {best.flip_rate*100:.1f}% > 1%")
                if best.avg_cost_per_event >= 0.01:
                    issues.append(f"Cost ${best.avg_cost_per_event:.4f} >= $0.01")
                recommendation += ", ".join(issues)

        return Scoreboard(
            timestamp=datetime.utcnow().isoformat(),
            test_events=test_events,
            k_consistency=self.k_consistency,
            results=sorted_results,
            winner=winner,
            recommendation=recommendation,
        )

    def to_markdown(self, scoreboard: Scoreboard) -> str:
        """
        Convert scoreboard to markdown.

        Args:
            scoreboard: Evaluation scoreboard

        Returns:
            Markdown string
        """
        lines = []
        lines.append("# Model Evaluation Scoreboard")
        lines.append("")
        lines.append(f"**Generated:** {scoreboard.timestamp}")
        lines.append(f"**Test Events:** {scoreboard.test_events}")
        lines.append(f"**K for Consistency:** {scoreboard.k_consistency}")
        lines.append("")

        lines.append("## Results")
        lines.append("")
        lines.append(
            "| Model | Prompt | JSON OK | Flip Rate | Score Std | Cost/Event | p95 Latency |"
        )
        lines.append(
            "|-------|--------|---------|-----------|-----------|------------|-------------|"
        )

        for r in scoreboard.results:
            lines.append(
                f"| {r.model} | {r.prompt_version} | "
                f"{r.json_valid_rate*100:.1f}% | "
                f"{r.flip_rate*100:.1f}% | "
                f"{r.avg_score_std:.3f} | "
                f"${r.avg_cost_per_event:.4f} | "
                f"{r.latency_p95:.0f}ms |"
            )

        lines.append("")

        if scoreboard.winner:
            lines.append(f"## Winner: {scoreboard.winner}")
        else:
            lines.append("## No Clear Winner")

        lines.append("")
        lines.append(f"**Recommendation:** {scoreboard.recommendation}")

        return "\n".join(lines)
