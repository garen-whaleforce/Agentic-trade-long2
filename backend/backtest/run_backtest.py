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


# ============================================
# CLI Entry Point
# ============================================

if __name__ == "__main__":
    import argparse
    import asyncio
    import sys
    from datetime import datetime

    parser = argparse.ArgumentParser(
        description="Run backtest via Whaleforce API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backend.backtest.run_backtest --start 2024-01-01 --end 2024-03-31
  python -m backend.backtest.run_backtest --period tune
  python -m backend.backtest.run_backtest --period validate --dry-run
        """,
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--period",
        type=str,
        choices=["tune", "validate", "final", "2024Q1", "2024Q2", "2024Q3", "2024Q4"],
        help="Predefined period to run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run (don't submit to Whaleforce)",
    )
    parser.add_argument(
        "--signals-file",
        type=str,
        help="Path to signals CSV file",
    )

    args = parser.parse_args()

    # Predefined periods
    PERIODS = {
        "tune": ("2017-01-01", "2021-12-31"),
        "validate": ("2022-01-01", "2023-12-31"),
        "final": ("2024-01-01", "2025-12-31"),
        "2024Q1": ("2024-01-01", "2024-03-31"),
        "2024Q2": ("2024-04-01", "2024-06-30"),
        "2024Q3": ("2024-07-01", "2024-09-30"),
        "2024Q4": ("2024-10-01", "2024-12-31"),
    }

    # Determine date range
    if args.period:
        start_str, end_str = PERIODS[args.period]
    elif args.start and args.end:
        start_str, end_str = args.start, args.end
    else:
        print("Error: Must specify either --period or both --start and --end")
        sys.exit(1)

    start_date = date.fromisoformat(start_str)
    end_date = date.fromisoformat(end_str)

    print(f"Backtest Configuration:")
    print(f"  Period: {start_str} to {end_str}")
    print(f"  Dry run: {args.dry_run}")
    print()

    async def main():
        from backtest.full_backtest_runner import FullBacktestRunner, BacktestRunConfig

        run_id = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        period_type = args.period or "custom"

        config = BacktestRunConfig(
            run_id=run_id,
            purpose=f"CLI backtest: {period_type}",
            period_type=period_type,
            start_date=start_str,
            end_date=end_str,
            dry_run=args.dry_run,
        )

        runner = FullBacktestRunner(config)
        print(f"Starting backtest run: {run_id}")

        result = await runner.run()

        print()
        print("=" * 50)
        print("Backtest Complete")
        print("=" * 50)
        print(f"Run ID: {result['run_id']}")
        print(f"Events analyzed: {result['processed_events']}")
        print(f"Trade signals: {result['trade_signals']}")
        print(f"No trade signals: {result['no_trade_signals']}")

        if not args.dry_run and "backtest_result" in result:
            bt = result["backtest_result"]
            if "performance" in bt:
                perf = bt["performance"]
                print()
                print("Performance (from Whaleforce API):")
                print(f"  CAGR: {perf.get('cagr', 0) * 100:.1f}%")
                print(f"  Sharpe: {perf.get('sharpe_ratio', 0):.2f}")
                print(f"  Win Rate: {perf.get('win_rate', 0) * 100:.1f}%")
                print(f"  Max Drawdown: {perf.get('max_drawdown', 0) * 100:.1f}%")

        print()
        print(f"Artifacts saved to: runs/{run_id}/")

    asyncio.run(main())
