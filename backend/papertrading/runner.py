"""
Paper Trading Runner.

Main entry point for paper trading execution.

This runs daily to:
1. Check for new earnings events
2. Analyze events with LLM
3. Generate trade signals
4. Record positions
5. Generate daily report
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from pydantic import BaseModel

from core.config import settings
from core.trading_calendar import TradingCalendar, is_trading_day, calculate_trading_dates
from services.earningscall_client import EarningsCallClient
from llm.score_only_runner import ScoreOnlyRunner
from signals.gate import SignalGate
from signals.artifact_logger import ArtifactLogger, RunConfig
from .freeze_policy import FreezePolicy, get_frozen_config, require_frozen, validate_runtime
from .order_book import PaperOrderBook, get_order_book
from .monitoring import (
    get_metrics,
    get_alerts,
    AlertSeverity,
    DailyReporter,
)


logger = logging.getLogger("paper_trading")


class PaperTradingConfig(BaseModel):
    """Paper trading configuration."""

    enabled: bool = True
    dry_run: bool = False  # If True, analyze but don't record positions
    run_time: str = "18:00"  # Time to run daily (after market close)
    lookback_days: int = 1  # Days to look back for events
    frozen_config_path: str = "backend/papertrading/frozen_config.json"


class DailyRunResult(BaseModel):
    """Result of a daily paper trading run."""

    run_id: str
    run_date: str
    status: str
    events_found: int
    events_analyzed: int
    trade_signals: int
    no_trade_signals: int
    positions_opened: int
    positions_closed: int
    errors: List[str]


class PaperTradingRunner:
    """
    Runs daily paper trading pipeline.

    IMPORTANT: Uses frozen configuration. Any change to
    configuration requires new version and full revalidation.
    """

    def __init__(
        self,
        config: Optional[PaperTradingConfig] = None,
    ):
        """
        Initialize runner.

        Args:
            config: Paper trading configuration
        """
        self.config = config or PaperTradingConfig()
        self.calendar = TradingCalendar()
        self.earnings_client = EarningsCallClient()
        self.order_book = get_order_book()
        self.artifact_logger = ArtifactLogger(base_dir="runs/paper")
        self.metrics = get_metrics()
        self.alerts = get_alerts()

        # Load frozen config (strict mode for paper trading)
        self.freeze_policy = FreezePolicy()
        # In paper trading, we require frozen config
        try:
            self.frozen = require_frozen()
        except ValueError:
            # Allow non-frozen for testing/dry-run, but will fail at runtime check
            self.frozen = get_frozen_config()

        # Initialize analyzer with frozen settings
        self.analyzer = ScoreOnlyRunner(
            model=self.frozen.model,
            prompt_version=self.frozen.prompt_version,
        )

        # Initialize gate with frozen thresholds
        self.gate = SignalGate(
            score_threshold=self.frozen.score_threshold,
            evidence_min_count=self.frozen.evidence_min_count,
        )

    async def run_daily(self, run_date: Optional[date] = None) -> DailyRunResult:
        """
        Run daily paper trading pipeline.

        Args:
            run_date: Date to run for (default: today)

        Returns:
            DailyRunResult
        """
        run_date = run_date or date.today()
        run_id = f"paper_{run_date.isoformat()}_{datetime.now().strftime('%H%M%S')}"

        logger.info(f"Starting paper trading run: {run_id}")

        result = DailyRunResult(
            run_id=run_id,
            run_date=str(run_date),
            status="running",
            events_found=0,
            events_analyzed=0,
            trade_signals=0,
            no_trade_signals=0,
            positions_opened=0,
            positions_closed=0,
            errors=[],
        )

        try:
            # Check if trading day
            if not is_trading_day(run_date):
                logger.info(f"{run_date} is not a trading day, skipping")
                result.status = "skipped_non_trading_day"
                return result

            # Check freeze policy - validate runtime configuration matches frozen manifest
            try:
                validate_runtime(
                    batch_score_model=self.frozen.model,
                    prompt_version=self.frozen.prompt_version,
                    score_threshold=self.frozen.score_threshold,
                    evidence_min_count=self.frozen.evidence_min_count,
                )
            except ValueError as e:
                self.alerts.raise_alert(
                    AlertSeverity.CRITICAL,
                    "Freeze Policy Violation",
                    str(e),
                )
                result.status = "error_not_frozen"
                result.errors.append(str(e))
                return result

            # Create run directory
            run_config = RunConfig(
                run_id=run_id,
                timestamp=datetime.utcnow().isoformat(),
                purpose="Paper trading daily run",
                date_range={"start": str(run_date), "end": str(run_date)},
                models={"batch_score": self.frozen.model},
                prompt_versions={"batch_score": self.frozen.prompt_version},
                thresholds={
                    "score_threshold": self.frozen.score_threshold,
                    "evidence_min_count": self.frozen.evidence_min_count,
                },
                frozen=True,
            )
            self.artifact_logger.create_run(run_config)

            # Step 1: Get events from yesterday (published after market)
            lookback_start = run_date - timedelta(days=self.config.lookback_days)
            events = await self._fetch_events(lookback_start, run_date)
            result.events_found = len(events)
            self.metrics.record("events_found", len(events))

            if not events:
                logger.info("No new events found")
                result.status = "completed_no_events"
                return result

            # Step 2: Analyze events
            signals = await self._analyze_events(run_id, events)
            result.events_analyzed = len(signals)

            # Step 3: Apply gate and create positions
            for signal in signals:
                if signal.get("error"):
                    result.errors.append(f"{signal['event_id']}: {signal['error']}")
                    continue

                gate_result = self.gate.evaluate(signal)

                if gate_result.trade_long:
                    result.trade_signals += 1
                    self.metrics.record("trade_signal", 1)

                    if not self.config.dry_run:
                        position = await self._open_position(signal)
                        if position:
                            result.positions_opened += 1
                else:
                    result.no_trade_signals += 1
                    self.metrics.record("no_trade_signal", 1)

            # Step 4: Check for positions to close
            closed = await self._close_due_positions(run_date)
            result.positions_closed = closed

            # Step 5: Log summary
            self.artifact_logger.log_summary(run_id, result.model_dump())

            result.status = "completed"
            logger.info(f"Paper trading run completed: {result}")

        except Exception as e:
            logger.exception(f"Paper trading run failed: {e}")
            result.status = "error"
            result.errors.append(str(e))

            self.alerts.raise_alert(
                AlertSeverity.CRITICAL,
                "Paper Trading Run Failed",
                str(e),
            )

        return result

    async def _fetch_events(
        self,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Fetch earnings events."""
        try:
            events = await self.earnings_client.get_events_in_range(
                start_date=str(start_date),
                end_date=str(end_date),
            )
            return events
        except Exception as e:
            logger.error(f"Failed to fetch events: {e}")
            self.alerts.raise_alert(
                AlertSeverity.WARNING,
                "Event Fetch Failed",
                str(e),
            )
            return []

    async def _analyze_events(
        self,
        run_id: str,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Analyze events with LLM."""
        signals = []

        for event in events:
            try:
                start_time = datetime.now()

                # Get transcript
                transcript = await self.earnings_client.get_transcript(
                    event["event_id"]
                )

                # Run analysis
                analysis = await self.analyzer.analyze(
                    event_id=event["event_id"],
                    transcript=transcript,
                )

                # Record metrics
                latency = (datetime.now() - start_time).total_seconds() * 1000
                self.metrics.record("analysis_latency", latency)
                self.metrics.record("llm_cost", analysis.get("cost_usd", 0))
                self.metrics.record("signal_analyzed", 1)

                # Log artifacts
                self.artifact_logger.log_llm_request(
                    run_id,
                    event["event_id"],
                    {"event": event},
                )
                self.artifact_logger.log_llm_response(
                    run_id,
                    event["event_id"],
                    analysis,
                )

                analysis["event"] = event
                signals.append(analysis)

            except Exception as e:
                logger.error(f"Failed to analyze {event['event_id']}: {e}")
                signals.append({
                    "event_id": event["event_id"],
                    "error": str(e),
                })

        return signals

    async def _open_position(
        self,
        signal: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Open a paper trading position."""
        try:
            event = signal["event"]
            event_date = date.fromisoformat(event["event_date"])

            # Use SSOT trading calendar for correct date calculation
            # Entry = T+1 close, Exit = T+30 close (from T, not from entry)
            trading_dates = calculate_trading_dates(event_date)
            entry_date = trading_dates["entry_date"]
            exit_date = trading_dates["exit_date"]

            position = self.order_book.open_position(
                symbol=event["symbol"],
                entry_date=entry_date,
                exit_date=exit_date,
                signal_id=event["event_id"],
                score=signal.get("score", 0),
            )

            self.metrics.record("position_opened", 1)
            logger.info(f"Opened position: {position}")

            return position

        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return None

    async def _close_due_positions(self, as_of_date: date) -> int:
        """Close positions that are due to exit."""
        try:
            closed = self.order_book.close_due_positions(as_of_date)
            if closed:
                self.metrics.record("positions_closed", len(closed))
                logger.info(f"Closed {len(closed)} positions")
            return len(closed)
        except Exception as e:
            logger.error(f"Failed to close positions: {e}")
            return 0


async def run_paper_trading_daily() -> DailyRunResult:
    """
    Convenience function to run daily paper trading.

    Returns:
        DailyRunResult
    """
    runner = PaperTradingRunner()
    return await runner.run_daily()


async def run_paper_trading_backfill(
    start_date: date,
    end_date: date,
) -> List[DailyRunResult]:
    """
    Backfill paper trading for a date range.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        List of daily results
    """
    runner = PaperTradingRunner()
    results = []

    current = start_date
    while current <= end_date:
        result = await runner.run_daily(current)
        results.append(result)
        current += timedelta(days=1)

    return results


if __name__ == "__main__":
    # Run paper trading
    asyncio.run(run_paper_trading_daily())
