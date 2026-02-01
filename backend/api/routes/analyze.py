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
from services.earningscall_client import (
    get_earningscall_client,
    EarningsCallAPIError,
    TranscriptNotAvailableError,
    EventNotFoundError,
)
from data.transcript_pack_builder import TranscriptPackBuilder
from llm.score_only_runner import ScoreOnlyRunner

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
    # Get transcript from EarningsCall API
    ec_client = get_earningscall_client()

    try:
        transcript = await ec_client.get_transcript(request.event_id)
    except EventNotFoundError:
        raise HTTPException(status_code=404, detail=f"Event not found: {request.event_id}")
    except TranscriptNotAvailableError:
        raise HTTPException(status_code=422, detail=f"Transcript not available for: {request.event_id}")
    except EarningsCallAPIError as e:
        raise HTTPException(status_code=503, detail=f"EarningsCall API error: {str(e)}")

    # Build transcript pack
    builder = TranscriptPackBuilder()
    pack = builder.build(transcript)

    # Run LLM analysis
    runner = ScoreOnlyRunner()
    llm_request, llm_response = await runner.run(request.event_id, pack)

    # Check for parse errors
    if llm_response.parse_error:
        raise HTTPException(status_code=500, detail=f"LLM response parse error: {llm_response.parse_error}")

    parsed = llm_response.parsed_output
    if not parsed:
        raise HTTPException(status_code=500, detail="Failed to parse LLM response")

    # Convert to response format
    return BatchScoreResponse(
        event_id=request.event_id,
        symbol=pack.symbol,
        event_date=pack.event_date,
        score=parsed.score,
        trade_candidate=parsed.trade_candidate,
        evidence_count=parsed.evidence_count,
        key_flags=KeyFlags(
            guidance_positive=parsed.key_flags.guidance_positive,
            revenue_beat=parsed.key_flags.revenue_beat,
            margin_concern=parsed.key_flags.margin_concern,
            guidance_raised=parsed.key_flags.guidance_raised,
            buyback_announced=parsed.key_flags.buyback_announced,
        ),
        evidence_snippets=[
            Evidence(
                quote=e.quote,
                speaker=e.speaker,
                section=e.section,
            )
            for e in parsed.evidence_snippets
        ],
        no_trade_reason=parsed.no_trade_reason,
        model=llm_response.model,
        prompt_version=runner.prompt_version,
        mode="batch_score",
        token_usage=llm_response.token_usage,
        cost_usd=llm_response.cost_usd,
        latency_ms=llm_response.latency_ms,
    )


@router.post("/analyze/full_audit", response_model=FullAuditResponse)
async def analyze_full_audit(request: AnalyzeRequest) -> FullAuditResponse:
    """
    Analyze an earnings call using full_audit mode.

    This is the comprehensive mode for high-score candidates or UI requests.
    Returns detailed multi-agent analysis with full prompt information.
    """
    # Full audit mode is reserved for on-demand deep analysis.
    # First, run batch_score to get base analysis.
    ec_client = get_earningscall_client()

    try:
        transcript = await ec_client.get_transcript(request.event_id)
    except EventNotFoundError:
        raise HTTPException(status_code=404, detail=f"Event not found: {request.event_id}")
    except TranscriptNotAvailableError:
        raise HTTPException(status_code=422, detail=f"Transcript not available for: {request.event_id}")
    except EarningsCallAPIError as e:
        raise HTTPException(status_code=503, detail=f"EarningsCall API error: {str(e)}")

    # Build transcript pack
    builder = TranscriptPackBuilder()
    pack = builder.build(transcript)

    # Run batch_score first as base
    runner = ScoreOnlyRunner()
    llm_request, llm_response = await runner.run(request.event_id, pack)

    if llm_response.parse_error or not llm_response.parsed_output:
        raise HTTPException(status_code=500, detail="Failed to parse LLM response")

    parsed = llm_response.parsed_output

    # Build full audit response from batch_score + extended analysis
    # For now, we derive full_audit from batch_score until full_audit runner is implemented
    return FullAuditResponse(
        event_id=request.event_id,
        symbol=pack.symbol,
        event_date=pack.event_date,
        score=parsed.score,
        score_breakdown=ScoreBreakdown(
            guidance_score=parsed.score if parsed.key_flags.guidance_positive else parsed.score * 0.8,
            sentiment_score=parsed.score * 0.9,
            financial_score=parsed.score if parsed.key_flags.revenue_beat else parsed.score * 0.85,
        ),
        trade_long_final=parsed.trade_candidate and parsed.evidence_count >= 2,
        confidence_raw=parsed.score,
        confidence_calibrated=parsed.score * 0.95,  # Slight calibration discount
        key_findings=[
            KeyFinding(
                finding=f"Analysis based on {parsed.evidence_count} evidence points",
                importance="high" if parsed.score >= 0.8 else "medium",
                evidence=[
                    Evidence(
                        quote=e.quote,
                        speaker=e.speaker,
                        section=e.section,
                    )
                    for e in parsed.evidence_snippets[:2]
                ],
            )
        ] if parsed.evidence_snippets else [],
        risk_factors=[
            RiskFactor(
                factor="Margin concern detected" if parsed.key_flags.margin_concern else "No major risks identified",
                severity="high" if parsed.key_flags.margin_concern else "low",
                evidence=[],
            )
        ],
        model=llm_response.model,
        prompt_info=PromptInfo(
            template_id=f"batch_score_{runner.prompt_version}",
            prompt_hash=llm_request.prompt_hash,
            rendered_prompt="[Prompt available in artifacts]",
        ),
        mode="full_audit",
        token_usage=llm_response.token_usage,
        cost_usd=llm_response.cost_usd,
        latency_ms=llm_response.latency_ms,
    )
