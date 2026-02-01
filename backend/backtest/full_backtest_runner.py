"""
Full Backtest Runner.

Orchestrates the complete backtest process:
1. Load events from Earnings Call API
2. Run LLM analysis (batch_score)
3. Apply signal gate
4. Submit to Whaleforce Backtest API
5. Generate report

IMPORTANT: All performance metrics come from Whaleforce API.
Do NOT calculate CAGR, Sharpe, etc. locally.
"""

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from pydantic import BaseModel

from core.config import settings
from core.trading_calendar import TradingCalendar, calculate_trading_dates
from services.earningscall_client import EarningsCallClient
from services.whaleforce_backtest_client import (
    WhaleforceBacktestClient,
    Position,
    BacktestConfig,
)
from llm.score_only_runner import ScoreOnlyRunner
from signals.gate import SignalGate
from signals.artifact_logger import ArtifactLogger, RunConfig
from research.walk_forward import WALK_FORWARD_PERIODS


class BacktestRunConfig(BaseModel):
    """Configuration for a backtest run."""

    run_id: str
    purpose: str
    period_type: str  # "tune", "validate", "final", "paper"
    start_date: str
    end_date: str
    score_threshold: float = 0.70
    evidence_min_count: int = 2
    model: str = "gpt-4o-mini"
    prompt_version: str = "batch_score_v1.0.0"
    dry_run: bool = False  # If True, don't submit to Whaleforce


class BacktestProgress(BaseModel):
    """Progress tracking for backtest."""

    total_events: int = 0
    processed_events: int = 0
    trade_signals: int = 0
    no_trade_signals: int = 0
    errors: int = 0
    current_phase: str = "initializing"


class FullBacktestRunner:
    """
    Runs full backtest pipeline.

    Phases:
    1. Initialize: Load config, create run directory
    2. Fetch: Get earnings events from API
    3. Analyze: Run LLM analysis on each event
    4. Gate: Apply trade decision gate
    5. Submit: Submit positions to Whaleforce API
    6. Report: Generate report with API results
    """

    def __init__(
        self,
        config: BacktestRunConfig,
        earnings_client: Optional[EarningsCallClient] = None,
        backtest_client: Optional[WhaleforceBacktestClient] = None,
    ):
        """
        Initialize runner.

        Args:
            config: Backtest configuration
            earnings_client: Earnings call API client
            backtest_client: Whaleforce backtest API client
        """
        self.config = config
        self.earnings_client = earnings_client or EarningsCallClient()
        self.backtest_client = backtest_client or WhaleforceBacktestClient()
        self.analyzer = ScoreOnlyRunner(model=config.model)
        self.gate = SignalGate(
            score_threshold=config.score_threshold,
            evidence_min_count=config.evidence_min_count,
        )
        self.logger = ArtifactLogger()
        self.calendar = TradingCalendar()
        self.progress = BacktestProgress()

    async def run(self) -> Dict[str, Any]:
        """
        Run full backtest pipeline.

        Returns:
            Dict with backtest results
        """
        try:
            # Phase 1: Initialize
            self.progress.current_phase = "initializing"
            run_dir = self._initialize_run()

            # Phase 2: Fetch events
            self.progress.current_phase = "fetching"
            events = await self._fetch_events()
            self.progress.total_events = len(events)

            # Phase 3: Analyze events
            self.progress.current_phase = "analyzing"
            signals = await self._analyze_events(events)

            # Phase 4: Apply gate
            self.progress.current_phase = "gating"
            positions = self._apply_gate(signals)

            # Phase 5: Submit to Whaleforce (unless dry run)
            self.progress.current_phase = "submitting"
            if not self.config.dry_run and positions:
                backtest_result = await self._submit_backtest(positions)
            else:
                backtest_result = {"status": "dry_run", "positions": len(positions)}

            # Phase 6: Generate report
            self.progress.current_phase = "reporting"
            report = self._generate_report(signals, positions, backtest_result)

            self.progress.current_phase = "completed"
            return report

        except Exception as e:
            self.progress.current_phase = f"error: {str(e)}"
            raise

    def _initialize_run(self) -> Path:
        """Initialize run directory and config."""
        run_config = RunConfig(
            run_id=self.config.run_id,
            timestamp=datetime.utcnow().isoformat(),
            purpose=self.config.purpose,
            date_range={
                "start": self.config.start_date,
                "end": self.config.end_date,
            },
            models={"batch_score": self.config.model},
            prompt_versions={"batch_score": self.config.prompt_version},
            thresholds={
                "score_threshold": self.config.score_threshold,
                "evidence_min_count": self.config.evidence_min_count,
            },
        )
        return self.logger.create_run(run_config)

    async def _fetch_events(self) -> List[Dict[str, Any]]:
        """Fetch earnings events from API."""
        events = await self.earnings_client.get_events_in_range(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
        )
        return events

    async def _analyze_events(
        self,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Analyze each event with LLM."""
        signals = []

        for event in events:
            try:
                # Get transcript
                transcript = await self.earnings_client.get_transcript(
                    event["event_id"]
                )

                # Run analysis
                analysis = await self.analyzer.analyze(
                    event_id=event["event_id"],
                    transcript=transcript,
                )

                # Log request/response
                self.logger.log_llm_request(
                    self.config.run_id,
                    event["event_id"],
                    {"event": event, "model": self.config.model},
                )
                self.logger.log_llm_response(
                    self.config.run_id,
                    event["event_id"],
                    analysis,
                )

                # Add event metadata
                analysis["event"] = event
                analysis["trading_dates"] = calculate_trading_dates(
                    date.fromisoformat(event["event_date"])
                )

                signals.append(analysis)
                self.progress.processed_events += 1

            except Exception as e:
                self.progress.errors += 1
                signals.append({
                    "event_id": event["event_id"],
                    "error": str(e),
                    "trade_long": False,
                })

        return signals

    def _apply_gate(
        self,
        signals: List[Dict[str, Any]],
    ) -> List[Position]:
        """Apply trade decision gate to signals."""
        positions: List[Position] = []

        for signal in signals:
            if signal.get("error"):
                self.progress.no_trade_signals += 1
                continue

            # Apply gate
            gate_result = self.gate.evaluate(signal)

            if gate_result.trade_long:
                self.progress.trade_signals += 1

                # Build position as proper Position object
                trading_dates = signal.get("trading_dates", {})
                position = Position(
                    symbol=signal["event"]["symbol"],
                    entry_date=str(trading_dates.get("entry_date")),
                    exit_date=str(trading_dates.get("exit_date")),
                    direction="long",
                    signal_id=signal.get("event_id", signal["event"].get("event_id", "")),
                    score=signal.get("score", 0.0),
                )
                positions.append(position)
            else:
                self.progress.no_trade_signals += 1

        return positions

    async def _submit_backtest(
        self,
        positions: List[Position],
    ) -> Dict[str, Any]:
        """
        Submit positions to Whaleforce Backtest API.

        IMPORTANT: All performance metrics come from this API.
        Do NOT calculate them locally.
        """
        # Build backtest config
        backtest_config = BacktestConfig(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
        )

        # Log request
        request = {
            "strategy_id": self.config.run_id,
            "positions": [p.model_dump() for p in positions],
            "config": backtest_config.model_dump(),
        }
        self.logger.log_backtest_request(self.config.run_id, request)

        # Submit to API with correct signature
        result = await self.backtest_client.run_backtest(
            strategy_id=self.config.run_id,
            positions=positions,
            config=backtest_config,
        )

        # Log result - convert to dict if it's a model
        result_dict = result.model_dump() if hasattr(result, "model_dump") else result
        self.logger.log_backtest_result(self.config.run_id, result_dict)

        return result_dict

    def _generate_report(
        self,
        signals: List[Dict[str, Any]],
        positions: List[Position],
        backtest_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate final report."""
        summary = {
            "run_id": self.config.run_id,
            "period_type": self.config.period_type,
            "date_range": {
                "start": self.config.start_date,
                "end": self.config.end_date,
            },
            "total_events": self.progress.total_events,
            "processed_events": self.progress.processed_events,
            "trade_signals": self.progress.trade_signals,
            "no_trade_signals": self.progress.no_trade_signals,
            "errors": self.progress.errors,
            "positions_submitted": len(positions),
            "backtest_result": backtest_result,
        }

        # Log summary
        self.logger.log_summary(self.config.run_id, summary)

        # Generate markdown report
        self.logger.generate_report(
            run_id=self.config.run_id,
            config=RunConfig(
                run_id=self.config.run_id,
                timestamp=datetime.utcnow().isoformat(),
                purpose=self.config.purpose,
                date_range={
                    "start": self.config.start_date,
                    "end": self.config.end_date,
                },
                models={"batch_score": self.config.model},
                prompt_versions={"batch_score": self.config.prompt_version},
                thresholds={
                    "score_threshold": self.config.score_threshold,
                    "evidence_min_count": self.config.evidence_min_count,
                },
            ),
            summary=summary,
            backtest_result=backtest_result if not self.config.dry_run else None,
        )

        return summary


async def run_tune_period(dry_run: bool = True) -> Dict[str, Any]:
    """Run backtest on tune period (2017-2021)."""
    periods = WALK_FORWARD_PERIODS
    tune = periods["tune"]

    config = BacktestRunConfig(
        run_id=f"tune_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        purpose="Tune period backtest",
        period_type="tune",
        start_date=tune["start"],
        end_date=tune["end"],
        dry_run=dry_run,
    )

    runner = FullBacktestRunner(config)
    return await runner.run()


async def run_validate_period(dry_run: bool = True) -> Dict[str, Any]:
    """Run backtest on validate period (2022-2023)."""
    periods = WALK_FORWARD_PERIODS
    validate = periods["validate"]

    config = BacktestRunConfig(
        run_id=f"validate_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        purpose="Validate period backtest",
        period_type="validate",
        start_date=validate["start"],
        end_date=validate["end"],
        dry_run=dry_run,
    )

    runner = FullBacktestRunner(config)
    return await runner.run()


async def run_final_period(dry_run: bool = True) -> Dict[str, Any]:
    """
    Run backtest on final test period (2024-2025).

    WARNING: After running final test, parameters CANNOT be changed.
    """
    periods = WALK_FORWARD_PERIODS
    final = periods["final"]

    config = BacktestRunConfig(
        run_id=f"final_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        purpose="Final test period backtest - NO PARAMETER CHANGES AFTER THIS",
        period_type="final",
        start_date=final["start"],
        end_date=final["end"],
        dry_run=dry_run,
    )

    runner = FullBacktestRunner(config)
    return await runner.run()
