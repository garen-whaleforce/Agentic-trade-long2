"""
Analysis endpoints.

LLM-powered earnings call analysis with two modes:
- batch_score: Quick, low-cost scoring (< $0.01/event)
- full_audit: Comprehensive analysis for high-score candidates
"""

from datetime import datetime
from typing import List, Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import settings

router = APIRouter()


# =====================================
# Schemas
# =====================================


class Evidence(BaseModel):
    """Evidence supporting a finding."""

    quote: str
    speaker: str
    section: Literal["prepared", "qa"]
    paragraph_index: Optional[int] = None
    relevance: Optional[str] = None


class KeyFlags(BaseModel):
    """Key flags extracted from transcript."""

    guidance_positive: bool = False
    revenue_beat: bool = False
    margin_concern: bool = False
    guidance_raised: bool = False
    buyback_announced: bool = False


class AnalyzeRequest(BaseModel):
    """Request for analysis."""

    event_id: str
    mode: Literal["batch_score", "full_audit"] = "batch_score"


class BatchScoreResponse(BaseModel):
    """Response for batch_score mode."""

    event_id: str
    symbol: str
    event_date: str
    score: float = Field(..., ge=0, le=1)
    trade_candidate: bool
    evidence_count: int
    key_flags: KeyFlags
    evidence_snippets: List[Evidence]
    no_trade_reason: Optional[str] = None

    # Metadata
    model: str
    prompt_version: str
    mode: Literal["batch_score"] = "batch_score"
    token_usage: dict
    cost_usd: float
    latency_ms: int


class ScoreBreakdown(BaseModel):
    """Breakdown of score components."""

    guidance_score: float
    sentiment_score: float
    financial_score: float


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


class PromptInfo(BaseModel):
    """Information about the prompt used."""

    template_id: str
    prompt_hash: str
    rendered_prompt: str


class FullAuditResponse(BaseModel):
    """Response for full_audit mode."""

    event_id: str
    symbol: str
    event_date: str

    # Scores
    score: float = Field(..., ge=0, le=1)
    score_breakdown: ScoreBreakdown
    trade_long_final: bool
    confidence_raw: float
    confidence_calibrated: float

    # Analysis
    key_findings: List[KeyFinding]
    risk_factors: List[RiskFactor]

    # Metadata
    model: str
    prompt_info: PromptInfo
    mode: Literal["full_audit"] = "full_audit"
    token_usage: dict
    cost_usd: float
    latency_ms: int


# =====================================
# Endpoints
# =====================================


@router.post("/analyze", response_model=BatchScoreResponse)
async def analyze_batch_score(request: AnalyzeRequest) -> BatchScoreResponse:
    """
    Analyze an earnings call using batch_score mode.

    This is the low-cost mode (< $0.01/event) for bulk processing.
    Returns a score and key flags with minimal output tokens.
    """
    # TODO: Implement actual LLM analysis
    # This is a stub response for now

    return BatchScoreResponse(
        event_id=request.event_id,
        symbol="AAPL",
        event_date="2024-01-25",
        score=0.82,
        trade_candidate=True,
        evidence_count=3,
        key_flags=KeyFlags(
            guidance_positive=True,
            revenue_beat=True,
            margin_concern=False,
            guidance_raised=True,
            buyback_announced=False,
        ),
        evidence_snippets=[
            Evidence(
                quote="We expect revenue growth of 15-18% next quarter",
                speaker="CFO",
                section="prepared",
                paragraph_index=12,
            ),
            Evidence(
                quote="Our pipeline is stronger than ever",
                speaker="CEO",
                section="qa",
                paragraph_index=45,
            ),
            Evidence(
                quote="Services revenue reached an all-time high",
                speaker="CFO",
                section="prepared",
                paragraph_index=8,
            ),
        ],
        no_trade_reason=None,
        model=settings.llm_batch_score_model,
        prompt_version="v1.2.0",
        mode="batch_score",
        token_usage={"input": 2500, "output": 350, "total": 2850},
        cost_usd=0.00058,
        latency_ms=1850,
    )


@router.post("/analyze/full_audit", response_model=FullAuditResponse)
async def analyze_full_audit(request: AnalyzeRequest) -> FullAuditResponse:
    """
    Analyze an earnings call using full_audit mode.

    This is the comprehensive mode for high-score candidates or UI requests.
    Returns detailed multi-agent analysis with full prompt information.
    """
    # TODO: Implement actual LLM analysis
    # This is a stub response for now

    return FullAuditResponse(
        event_id=request.event_id,
        symbol="AAPL",
        event_date="2024-01-25",
        score=0.82,
        score_breakdown=ScoreBreakdown(
            guidance_score=0.9,
            sentiment_score=0.75,
            financial_score=0.8,
        ),
        trade_long_final=True,
        confidence_raw=0.78,
        confidence_calibrated=0.74,
        key_findings=[
            KeyFinding(
                finding="Strong revenue guidance with 15-18% expected growth",
                importance="high",
                evidence=[
                    Evidence(
                        quote="We expect revenue growth of 15-18% next quarter",
                        speaker="CFO",
                        section="prepared",
                        paragraph_index=12,
                    ),
                    Evidence(
                        quote="This guidance reflects strong demand across all product lines",
                        speaker="CEO",
                        section="qa",
                        paragraph_index=28,
                    ),
                ],
            ),
            KeyFinding(
                finding="Services segment showing continued momentum",
                importance="medium",
                evidence=[
                    Evidence(
                        quote="Services revenue reached an all-time high of $23 billion",
                        speaker="CFO",
                        section="prepared",
                        paragraph_index=8,
                    ),
                ],
            ),
        ],
        risk_factors=[
            RiskFactor(
                factor="Supply chain concerns mentioned but manageable",
                severity="low",
                evidence=[
                    Evidence(
                        quote="We continue to monitor supply chain closely",
                        speaker="COO",
                        section="qa",
                        paragraph_index=52,
                    ),
                ],
            ),
        ],
        model=settings.llm_full_audit_model,
        prompt_info=PromptInfo(
            template_id="full_audit_v1.1.0",
            prompt_hash="sha256:abc123def456",
            rendered_prompt="[Full prompt would be here - truncated for brevity]",
        ),
        mode="full_audit",
        token_usage={"input": 6500, "output": 1200, "total": 7700},
        cost_usd=0.0036,
        latency_ms=4200,
    )
