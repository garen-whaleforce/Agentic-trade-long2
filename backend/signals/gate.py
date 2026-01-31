"""
Deterministic Gate.

Makes the final trade decision based on LLM output + rules.
LLM provides facts/scores, but the GATE makes the actual trade decision.

This ensures:
1. Consistent decisions (no LLM randomness in final output)
2. Explainable decisions (every NO_TRADE has a reason)
3. Conservative bias (fail-closed on uncertainty)
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel

from core.config import settings
from schemas.llm_output import BatchScoreOutput


class BlockReason(str, Enum):
    """Reasons for blocking a trade."""

    SCORE_TOO_LOW = "score_below_threshold"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    EVIDENCE_NOT_TRIANGULATED = "evidence_not_triangulated"
    MARGIN_CONCERN = "margin_concern_flagged"
    DATA_INCOMPLETE = "data_incomplete"
    SCHEMA_INVALID = "schema_validation_failed"
    LLM_DECLINED = "llm_recommended_no_trade"


class GateResult(BaseModel):
    """Result of the deterministic gate."""

    trade_long: bool
    block_reasons: List[BlockReason]
    passed_checks: List[str]
    final_score: float
    confidence: float

    # Metadata
    score_threshold_used: float
    evidence_min_used: int


class DeterministicGate:
    """
    Deterministic gate for trade decisions.

    The LLM outputs facts (score, evidence, flags).
    This gate applies RULES to determine trade_long.

    Rules:
    1. Score must be >= threshold
    2. Evidence count must be >= minimum
    3. Evidence must be triangulated (different sources)
    4. No critical red flags
    5. LLM must not have explicitly recommended no trade
    """

    def __init__(
        self,
        score_threshold: Optional[float] = None,
        evidence_min_count: Optional[int] = None,
        block_on_margin_concern: bool = True,
    ):
        """
        Initialize the gate.

        Args:
            score_threshold: Minimum score to pass (default from settings)
            evidence_min_count: Minimum evidence count (default from settings)
            block_on_margin_concern: Whether to block on margin concern flag
        """
        self.score_threshold = score_threshold or settings.strategy_score_threshold
        self.evidence_min_count = evidence_min_count or settings.strategy_evidence_min_count
        self.block_on_margin_concern = block_on_margin_concern

    def evaluate(
        self,
        llm_output: Optional[BatchScoreOutput],
        data_complete: bool = True,
    ) -> GateResult:
        """
        Evaluate LLM output through the deterministic gate.

        Args:
            llm_output: Output from batch_score LLM
            data_complete: Whether underlying data was complete

        Returns:
            GateResult with trade decision and reasons
        """
        block_reasons = []
        passed_checks = []

        # Handle invalid/missing output
        if llm_output is None:
            return GateResult(
                trade_long=False,
                block_reasons=[BlockReason.SCHEMA_INVALID],
                passed_checks=[],
                final_score=0.0,
                confidence=0.0,
                score_threshold_used=self.score_threshold,
                evidence_min_used=self.evidence_min_count,
            )

        # Check 1: Data completeness
        if not data_complete:
            block_reasons.append(BlockReason.DATA_INCOMPLETE)
        else:
            passed_checks.append("data_complete")

        # Check 2: Score threshold
        if llm_output.score >= self.score_threshold:
            passed_checks.append(f"score >= {self.score_threshold}")
        else:
            block_reasons.append(BlockReason.SCORE_TOO_LOW)

        # Check 3: Evidence count
        if llm_output.evidence_count >= self.evidence_min_count:
            passed_checks.append(f"evidence_count >= {self.evidence_min_count}")
        else:
            block_reasons.append(BlockReason.INSUFFICIENT_EVIDENCE)

        # Check 4: Evidence triangulation
        if self._check_triangulation(llm_output):
            passed_checks.append("evidence_triangulated")
        else:
            block_reasons.append(BlockReason.EVIDENCE_NOT_TRIANGULATED)

        # Check 5: Red flags
        if self.block_on_margin_concern and llm_output.key_flags.margin_concern:
            block_reasons.append(BlockReason.MARGIN_CONCERN)
        else:
            passed_checks.append("no_critical_red_flags")

        # Check 6: LLM recommendation
        if llm_output.trade_candidate:
            passed_checks.append("llm_recommended_trade")
        else:
            block_reasons.append(BlockReason.LLM_DECLINED)

        # Final decision: ALL checks must pass
        trade_long = len(block_reasons) == 0

        # Calculate confidence
        confidence = self._calculate_confidence(llm_output, len(passed_checks))

        return GateResult(
            trade_long=trade_long,
            block_reasons=block_reasons,
            passed_checks=passed_checks,
            final_score=llm_output.score,
            confidence=confidence,
            score_threshold_used=self.score_threshold,
            evidence_min_used=self.evidence_min_count,
        )

    def _check_triangulation(self, llm_output: BatchScoreOutput) -> bool:
        """
        Check if evidence is properly triangulated.

        Triangulation means evidence from different sources:
        - Different speakers, OR
        - Different sections (prepared vs qa)
        """
        if len(llm_output.evidence_snippets) < 2:
            return False

        speakers = set()
        sections = set()

        for evidence in llm_output.evidence_snippets:
            speakers.add(evidence.speaker)
            sections.add(evidence.section)

        # Either different speakers or different sections
        return len(speakers) > 1 or len(sections) > 1

    def _calculate_confidence(
        self, llm_output: BatchScoreOutput, checks_passed: int
    ) -> float:
        """
        Calculate calibrated confidence score.

        Factors:
        - Base score from LLM
        - Number of checks passed
        - Evidence quality
        """
        base = llm_output.score

        # Adjust for checks passed (max 6 checks)
        check_factor = checks_passed / 6

        # Adjust for evidence count
        evidence_factor = min(llm_output.evidence_count / 3, 1.0)

        # Weighted average
        confidence = 0.5 * base + 0.3 * check_factor + 0.2 * evidence_factor

        return round(min(max(confidence, 0.0), 1.0), 3)


# Global gate instance
_gate: Optional[DeterministicGate] = None


def get_gate() -> DeterministicGate:
    """Get the global deterministic gate."""
    global _gate
    if _gate is None:
        _gate = DeterministicGate()
    return _gate
