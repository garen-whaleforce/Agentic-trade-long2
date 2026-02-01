"""
Daily Scheduler for Paper Trading.

Runs the daily paper trading pipeline:
1. Fetch T-day earnings calls
2. Run batch_score analysis
3. Apply deterministic gate
4. Generate T+1 close entry orders
5. Schedule T+30 close exits
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
import uuid

from pydantic import BaseModel

from core.trading_calendar import (
    calculate_entry_date,
    calculate_exit_date,
    is_trading_day,
)
from .order_book import OrderBook, PaperOrder, OrderStatus
from .freeze_policy import FreezePolicy, get_freeze_policy


class SchedulerConfig(BaseModel):
    """Configuration for daily scheduler."""

    strategy_id: str
    batch_score_model: str
    full_audit_model: str
    prompt_version: str
    score_threshold: float
    evidence_min_count: int


class DailyRunResult(BaseModel):
    """Result from a daily scheduler run."""

    run_date: date
    run_id: str
    timestamp: str

    # Events processed
    events_found: int
    events_analyzed: int

    # Signals
    signals_generated: int
    trade_signals: int
    no_trade_signals: int

    # Orders
    orders_created: int
    entries_executed: int
    exits_executed: int

    # Cost
    total_cost_usd: float

    # Errors
    errors: List[str]


class DailyScheduler:
    """
    Daily paper trading scheduler.

    Flow:
    1. Validate freeze policy
    2. Fetch today's earnings calls
    3. Run analysis pipeline
    4. Generate orders for T+1 entry
    5. Process scheduled entries/exits
    6. Log artifacts
    """

    def __init__(
        self,
        config: SchedulerConfig,
        order_book: Optional[OrderBook] = None,
        freeze_policy: Optional[FreezePolicy] = None,
    ):
        """
        Initialize scheduler.

        Args:
            config: Scheduler configuration
            order_book: Order book instance
            freeze_policy: Freeze policy instance
        """
        self.config = config
        self.order_book = order_book or OrderBook()
        self.freeze_policy = freeze_policy or get_freeze_policy()

    def validate_freeze(self) -> None:
        """Validate configuration against freeze policy."""
        self.freeze_policy.validate_config(
            batch_score_model=self.config.batch_score_model,
            full_audit_model=self.config.full_audit_model,
            batch_score_prompt_version=self.config.prompt_version,
            score_threshold=self.config.score_threshold,
            evidence_min_count=self.config.evidence_min_count,
        )

    async def run_daily(
        self,
        run_date: Optional[date] = None,
        dry_run: bool = False,
    ) -> DailyRunResult:
        """
        Run daily paper trading pipeline.

        Args:
            run_date: Date to run for (default: today)
            dry_run: If True, don't actually execute orders

        Returns:
            DailyRunResult
        """
        run_date = run_date or date.today()
        run_id = f"paper_{run_date.isoformat()}_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        errors = []

        # Validate freeze policy
        try:
            self.validate_freeze()
        except ValueError as e:
            return DailyRunResult(
                run_date=run_date,
                run_id=run_id,
                timestamp=timestamp,
                events_found=0,
                events_analyzed=0,
                signals_generated=0,
                trade_signals=0,
                no_trade_signals=0,
                orders_created=0,
                entries_executed=0,
                exits_executed=0,
                total_cost_usd=0,
                errors=[str(e)],
            )

        # Pipeline phases:
        # Phase 1: Fetch events (requires EarningsCall API)
        # Phase 2: Run analysis (requires LLM)
        # Phase 3: Apply gate and generate orders
        # Phase 4: Execute pending entries/exits (requires market data)
        #
        # Note: Full pipeline implementation requires external services.
        # This scheduler handles order lifecycle; event fetching and analysis
        # are delegated to the paper trading runner (runner.py).

        events_found = 0
        events_analyzed = 0
        signals_generated = 0
        trade_signals = 0
        no_trade_signals = 0
        orders_created = 0

        # Process pending entries for today (fail-closed: no fake prices)
        entries_executed = 0
        if not dry_run:
            pending_entries = self.order_book.get_pending_entries(run_date)
            for order in pending_entries:
                # Market data integration required for real prices
                # Without market data, orders remain pending (fail-closed behavior)
                errors.append(
                    f"Entry pending for {order.order_id} ({order.symbol}): "
                    f"market data integration required for T+1 close price"
                )

        # Process pending exits for today (fail-closed: no fake prices)
        exits_executed = 0
        if not dry_run:
            pending_exits = self.order_book.get_pending_exits(run_date)
            for order in pending_exits:
                # Market data integration required for real prices
                # Without market data, orders remain pending (fail-closed behavior)
                errors.append(
                    f"Exit pending for {order.order_id} ({order.symbol}): "
                    f"market data integration required for T+30 close price"
                )

        return DailyRunResult(
            run_date=run_date,
            run_id=run_id,
            timestamp=timestamp,
            events_found=events_found,
            events_analyzed=events_analyzed,
            signals_generated=signals_generated,
            trade_signals=trade_signals,
            no_trade_signals=no_trade_signals,
            orders_created=orders_created,
            entries_executed=entries_executed,
            exits_executed=exits_executed,
            total_cost_usd=0,
            errors=errors,
        )

    async def dry_run_historical(
        self,
        start_date: date,
        end_date: date,
    ) -> List[DailyRunResult]:
        """
        Run dry-run simulation over historical dates.

        Useful for validating the pipeline before going live.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of daily run results
        """
        results = []
        current = start_date

        while current <= end_date:
            if is_trading_day(current):
                result = await self.run_daily(run_date=current, dry_run=True)
                results.append(result)
            current = current + timedelta(days=1)

        return results
