"""
Backtest Runner.

Orchestrates the backtest process:
1. Load signals
2. Convert to positions
3. Call Whaleforce API (SSOT)
4. Log artifacts
"""

from datetime import date
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

from services.whaleforce_backtest_client import (
    WhaleforceBacktestClient,
    Position,
    BacktestConfig,
    BacktestResult,
    get_backtest_client,
)
from schemas.signal import Signal
from signals.artifact_logger import get_artifact_logger


class BacktestRunResult(BaseModel):
    """Result from a backtest run."""

    run_id: str
    backtest_id: str
    strategy_id: str
    date_range: Dict[str, str]
    total_positions: int
    result: BacktestResult


class BacktestRunner:
    """
    Runs backtests via Whaleforce API.

    IMPORTANT: All performance metrics come from the API.
    This class only prepares positions and logs artifacts.
    """

    def __init__(
        self,
        client: Optional[WhaleforceBacktestClient] = None,
    ):
        """
        Initialize the runner.

        Args:
            client: Whaleforce client instance
        """
        self.client = client or get_backtest_client()
        self.logger = get_artifact_logger()

    def signals_to_positions(self, signals: List[Signal]) -> List[Position]:
        """
        Convert signals to positions for backtest.

        Only includes signals where trade_long is True.

        Args:
            signals: List of signals

        Returns:
            List of positions for backtest
        """
        positions = []

        for signal in signals:
            if not signal.trade_long:
                continue

            position = Position(
                symbol=signal.symbol,
                entry_date=signal.entry_date.isoformat(),
                exit_date=signal.exit_date.isoformat(),
                direction="long",
                sizing="equal_weight",
                signal_id=signal.signal_id,
                score=signal.score,
            )
            positions.append(position)

        return positions

    async def run(
        self,
        run_id: str,
        strategy_id: str,
        signals: List[Signal],
        start_date: date,
        end_date: date,
        initial_capital: float = 1000000,
    ) -> BacktestRunResult:
        """
        Run backtest for a set of signals.

        Args:
            run_id: Run identifier
            strategy_id: Strategy identifier
            signals: List of signals
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Initial capital

        Returns:
            BacktestRunResult with performance from API
        """
        # Convert signals to positions
        positions = self.signals_to_positions(signals)

        # Create config
        config = BacktestConfig(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            initial_capital=initial_capital,
        )

        # Log request
        request_data = {
            "strategy_id": strategy_id,
            "positions": [p.model_dump() for p in positions],
            "config": config.model_dump(),
        }
        self.logger.log_backtest_request(run_id, request_data)

        # Call API
        result = await self.client.run_backtest(strategy_id, positions, config)

        # Log result
        self.logger.log_backtest_result(run_id, result.model_dump())

        return BacktestRunResult(
            run_id=run_id,
            backtest_id=result.backtest_id,
            strategy_id=strategy_id,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            total_positions=len(positions),
            result=result,
        )


async def run_strategy_backtest(
    run_id: str,
    strategy_id: str,
    signals: List[Signal],
    start_date: date,
    end_date: date,
) -> BacktestRunResult:
    """Convenience function to run a strategy backtest."""
    runner = BacktestRunner()
    return await runner.run(
        run_id=run_id,
        strategy_id=strategy_id,
        signals=signals,
        start_date=start_date,
        end_date=end_date,
    )
