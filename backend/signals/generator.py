"""
Signal Generator.

Generates trade signals from LLM analysis output.
"""

import uuid
from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel

from core.trading_calendar import calculate_trading_dates
from schemas.signal import Signal, SignalOutput
from schemas.llm_output import BatchScoreOutput
from .gate import DeterministicGate, GateResult, get_gate


class SignalGeneratorResult(BaseModel):
    """Result from signal generation."""

    signal: Signal
    gate_result: GateResult
    signal_output: SignalOutput


class SignalGenerator:
    """
    Generates trade signals from LLM analysis.

    Flow:
    1. Receive LLM output (BatchScoreOutput)
    2. Apply deterministic gate
    3. Generate signal with all metadata
    4. Return SignalOutput for artifact logging
    """

    def __init__(self, gate: Optional[DeterministicGate] = None):
        """
        Initialize the generator.

        Args:
            gate: Deterministic gate instance
        """
        self.gate = gate or get_gate()

    def generate(
        self,
        event_id: str,
        symbol: str,
        event_date: date,
        llm_output: Optional[BatchScoreOutput],
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        run_id: str,
        batch_index: int = 0,
        data_complete: bool = True,
    ) -> SignalGeneratorResult:
        """
        Generate a trade signal.

        Args:
            event_id: Event identifier
            symbol: Stock symbol
            event_date: T day (earnings call date)
            llm_output: Output from batch_score analysis
            model: Model used
            prompt_version: Prompt version used
            input_tokens: Input token count
            output_tokens: Output token count
            cost_usd: Cost in USD
            latency_ms: Latency in milliseconds
            run_id: Run identifier
            batch_index: Index in batch
            data_complete: Whether data was complete

        Returns:
            SignalGeneratorResult with signal and metadata
        """
        # Calculate trading dates
        trading_dates = calculate_trading_dates(event_date)

        # Apply deterministic gate
        gate_result = self.gate.evaluate(llm_output, data_complete)

        # Generate signal ID
        signal_id = f"sig_{event_id}_{uuid.uuid4().hex[:8]}"

        # Determine no_trade_reason
        no_trade_reason = None
        if not gate_result.trade_long:
            reasons = [r.value for r in gate_result.block_reasons]
            no_trade_reason = "; ".join(reasons)

        # Create signal
        signal = Signal(
            event_id=event_id,
            signal_id=signal_id,
            symbol=symbol,
            event_date=event_date,
            entry_date=trading_dates["entry_date"],
            exit_date=trading_dates["exit_date"],
            score=gate_result.final_score,
            trade_long=gate_result.trade_long,
            confidence=gate_result.confidence,
            evidence_count=llm_output.evidence_count if llm_output else 0,
            no_trade_reason=no_trade_reason,
            model=model,
            prompt_version=prompt_version,
        )

        # Create signal output
        signal_output = SignalOutput(
            signal=signal,
            llm_request_hash=f"req_{event_id}",  # Would be actual hash
            llm_response_hash=f"resp_{event_id}",  # Would be actual hash
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            run_id=run_id,
            batch_index=batch_index,
        )

        return SignalGeneratorResult(
            signal=signal,
            gate_result=gate_result,
            signal_output=signal_output,
        )


def generate_signal(
    event_id: str,
    symbol: str,
    event_date: date,
    llm_output: Optional[BatchScoreOutput],
    model: str,
    prompt_version: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    run_id: str,
) -> SignalGeneratorResult:
    """Convenience function to generate a signal."""
    generator = SignalGenerator()
    return generator.generate(
        event_id=event_id,
        symbol=symbol,
        event_date=event_date,
        llm_output=llm_output,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        run_id=run_id,
    )
