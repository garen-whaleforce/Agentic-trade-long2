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
    entries_filled: int = 0  # PENDING -> OPEN with entry_price
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
            # PR7: Now includes prompt_hash validation for SSOT
            try:
                # Get current prompt_hash from analyzer for comparison
                current_prompt_hash = self.analyzer.prompt_hash if hasattr(self.analyzer, 'prompt_hash') else None

                validate_runtime(
                    batch_score_model=self.frozen.model,
                    prompt_version=self.frozen.prompt_version,
                    prompt_hash=current_prompt_hash,  # PR7: Pass prompt_hash for SSOT validation
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

            # Step 4: Fill pending entries (PENDING -> OPEN with entry_price)
            entries_filled = await self._fill_pending_entries(run_date)
            result.entries_filled = entries_filled
            if entries_filled:
                logger.info(f"Filled {entries_filled} pending entries")

            # Step 5: Check for positions to close
            closed = await self._close_due_positions(run_date)
            result.positions_closed = closed

            # Step 6: Log summary
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

                # Run analysis using .run() for complete LLMRequest/LLMResponse artifacts
                from data.transcript_pack_builder import TranscriptPackBuilder
                builder = TranscriptPackBuilder()
                pack = builder.build(transcript)

                llm_request, llm_response = await self.analyzer.run(
                    event_id=event["event_id"],
                    pack=pack,
                )

                # Build analysis dict from response (for gate evaluation)
                analysis = {
                    "event_id": event["event_id"],
                    "score": llm_response.parsed_output.score if llm_response.parsed_output else 0.0,
                    "trade_candidate": llm_response.parsed_output.trade_candidate if llm_response.parsed_output else False,
                    "evidence_count": llm_response.parsed_output.evidence_count if llm_response.parsed_output else 0,
                    "key_flags": llm_response.parsed_output.key_flags.model_dump() if llm_response.parsed_output else {},
                    "evidence_snippets": [e.model_dump() for e in llm_response.parsed_output.evidence_snippets] if llm_response.parsed_output else [],
                    "no_trade_reason": llm_response.parsed_output.no_trade_reason if llm_response.parsed_output else llm_response.parse_error,
                    "cost_usd": llm_response.cost_usd,
                    "latency_ms": llm_response.latency_ms,
                    "model": llm_response.model,
                    "prompt_version": self.analyzer.prompt_version,
                }

                # Record metrics
                latency = llm_response.latency_ms
                self.metrics.record("analysis_latency", latency)
                self.metrics.record("llm_cost", llm_response.cost_usd)
                self.metrics.record("signal_analyzed", 1)

                # Log complete LLMRequest/LLMResponse artifacts (includes prompt_hash, rendered_prompt, token_usage)
                self.artifact_logger.log_llm_request(
                    run_id,
                    event["event_id"],
                    llm_request.model_dump(),
                )
                self.artifact_logger.log_llm_response(
                    run_id,
                    event["event_id"],
                    llm_response.model_dump(),
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
                event_date=event_date,  # Pass actual event_date, not entry_date
                entry_date=entry_date,
                exit_date=exit_date,
                signal_id=event["event_id"],
                score=signal.get("score", 0),
                run_id=self.artifact_logger._current_run_id if hasattr(self.artifact_logger, '_current_run_id') else "paper",
                model=self.frozen.model,
                prompt_version=self.frozen.prompt_version,
            )

            self.metrics.record("position_opened", 1)
            logger.info(f"Opened position: {position}")

            return position

        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return None

    async def _fill_pending_entries(self, as_of_date: date) -> int:
        """
        Fill pending orders that should enter on the given date.

        This converts PENDING orders to OPEN positions by:
        1. Getting orders due to enter today
        2. Fetching entry prices from market data
        3. Marking orders as entered with actual prices

        Fail-closed: If price cannot be fetched, order stays PENDING.
        """
        from services.market_data_client import get_market_data_client

        try:
            client = get_market_data_client()
            pending_entries = self.order_book.get_pending_entries(as_of_date)

            if not pending_entries:
                return 0

            filled_count = 0
            for order in pending_entries:
                try:
                    # Get entry price (close price of entry_date)
                    entry_price = client.get_close_price(order.symbol, as_of_date)

                    if entry_price is None:
                        logger.warning(
                            f"No entry price for {order.symbol} on {as_of_date}, "
                            "order stays pending (fail-closed)"
                        )
                        continue

                    # Mark order as entered
                    self.order_book.mark_entered(order.order_id, entry_price)
                    filled_count += 1
                    logger.info(
                        f"Filled entry for {order.symbol}: "
                        f"order_id={order.order_id}, price={entry_price}"
                    )

                except Exception as e:
                    logger.error(f"Failed to fill entry for {order.order_id}: {e}")

            if filled_count:
                self.metrics.record("entries_filled", filled_count)

            return filled_count

        except Exception as e:
            logger.error(f"Failed to fill pending entries: {e}")
            return 0

    async def _close_due_positions(self, as_of_date: date) -> int:
        """Close positions that are due to exit."""
        from services.market_data_client import get_market_data_client

        try:
            client = get_market_data_client()

            # Price fetcher using market_data_client (synchronous)
            def price_fetcher(symbol: str, date_: date) -> Optional[float]:
                """Fetch closing price from market data source."""
                try:
                    return client.get_close_price(symbol, date_)
                except Exception as e:
                    logger.error(f"Failed to get price for {symbol} on {date_}: {e}")
                    return None

            closed = self.order_book.close_due_positions(as_of_date, price_fetcher=price_fetcher)
            if closed:
                self.metrics.record("positions_closed", len(closed))
                logger.info(f"Closed {len(closed)} positions")
            return len(closed)
        except ValueError as e:
            # Fail-closed triggered - log but don't crash
            logger.warning(f"Fail-closed triggered for position closing: {e}")
            return 0
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
