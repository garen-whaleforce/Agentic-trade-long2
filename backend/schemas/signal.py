"""
Signal schemas.

Defines the trade signal output format.
"""

from datetime import date, datetime
from typing import Optional, List, Literal

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """
    Trade signal from LLM analysis.

    Represents a potential trade opportunity based on earnings call analysis.
    """

    # Identifiers
    event_id: str
    signal_id: str
    symbol: str

    # Dates (from TimeAxis)
    event_date: date
    entry_date: date
    exit_date: date

    # LLM Output
    score: float = Field(..., ge=0, le=1)
    trade_long: bool
    confidence: float = Field(..., ge=0, le=1)
    evidence_count: int = Field(..., ge=0)

    # Decision factors
    no_trade_reason: Optional[str] = None

    # Metadata
    model: str
    prompt_version: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SignalOutput(BaseModel):
    """
    Complete signal output with all metadata for traceability.
    """

    signal: Signal

    # LLM request/response tracking
    llm_request_hash: str
    llm_response_hash: str

    # Token usage
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float

    # Timing
    latency_ms: int

    # Run context
    run_id: str
    batch_index: int

    def to_csv_row(self) -> dict:
        """Convert to CSV row format for signals.csv."""
        return {
            "event_id": self.signal.event_id,
            "signal_id": self.signal.signal_id,
            "symbol": self.signal.symbol,
            "event_date": self.signal.event_date.isoformat(),
            "entry_date": self.signal.entry_date.isoformat(),
            "exit_date": self.signal.exit_date.isoformat(),
            "score": self.signal.score,
            "trade_long": self.signal.trade_long,
            "confidence": self.signal.confidence,
            "evidence_count": self.signal.evidence_count,
            "no_trade_reason": self.signal.no_trade_reason,
            "model": self.signal.model,
            "prompt_version": self.signal.prompt_version,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "run_id": self.run_id,
        }
