"""
LLM output schemas.

Defines the expected output format from LLM analysis.
"""

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Evidence quote from transcript."""

    quote: str
    speaker: str
    section: Literal["prepared", "qa"]
    paragraph_index: Optional[int] = None
    relevance: Optional[str] = None
    supports: Optional[str] = None


class KeyFlags(BaseModel):
    """Key flags extracted from analysis."""

    guidance_positive: bool = False
    revenue_beat: bool = False
    margin_concern: bool = False
    guidance_raised: bool = False
    buyback_announced: bool = False


class BatchScoreOutput(BaseModel):
    """
    Output schema for batch_score mode.

    Minimal output to keep costs < $0.01/event.
    Target: 200-400 output tokens.
    """

    score: float = Field(..., ge=0, le=1, description="Overall score 0-1")
    trade_candidate: bool = Field(
        ..., description="Whether this is a trade candidate"
    )
    evidence_count: int = Field(..., ge=0, description="Number of evidence quotes")
    key_flags: KeyFlags = Field(..., description="Key signals extracted")
    evidence_snippets: List[Evidence] = Field(
        ..., min_length=0, max_length=5, description="Supporting evidence"
    )
    no_trade_reason: Optional[str] = Field(
        None, description="Reason for not trading (if trade_candidate=false)"
    )


class ScoreBreakdown(BaseModel):
    """Breakdown of score components."""

    guidance_score: float = Field(..., ge=0, le=1)
    sentiment_score: float = Field(..., ge=0, le=1)
    financial_score: float = Field(..., ge=0, le=1)


class KeyFinding(BaseModel):
    """Key finding from analysis."""

    finding: str
    importance: Literal["high", "medium", "low"]
    evidence: List[Evidence]


class RiskFactor(BaseModel):
    """Risk factor identified."""

    factor: str
    severity: Literal["high", "medium", "low"]
    evidence: List[Evidence]


class FullAuditOutput(BaseModel):
    """
    Output schema for full_audit mode.

    Comprehensive analysis for high-score candidates or UI display.
    """

    score: float = Field(..., ge=0, le=1)
    score_breakdown: ScoreBreakdown
    trade_long_final: bool
    confidence_raw: float = Field(..., ge=0, le=1)
    confidence_calibrated: float = Field(..., ge=0, le=1)

    key_findings: List[KeyFinding]
    risk_factors: List[RiskFactor]

    # Full evidence
    all_evidence: List[Evidence]

    # Summary
    summary: str
    recommendation: str
