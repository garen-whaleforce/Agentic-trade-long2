"""
Backtest endpoints.

All performance metrics come from Whaleforce Backtest API (SSOT).
Local calculation of CAGR, Sharpe, etc. is PROHIBITED.
"""

from datetime import date
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.whaleforce_backtest_client import (
    get_backtest_client,
    BacktestAPIError,
    APIConnectionError,
    InvalidPositionError,
    InsufficientDataError,
    Position as WFPosition,
    BacktestConfig as WFBacktestConfig,
)
from core.trading_calendar import get_trading_calendar

router = APIRouter()


# =====================================
# Schemas
# =====================================


class Position(BaseModel):
    """Single trading position."""

    symbol: str
    entry_date: str  # T+1 close
    exit_date: str  # T+30 close
    direction: str = "long"
    sizing: str = "equal_weight"
    signal_id: str
    score: float


class BacktestConfig(BaseModel):
    """Backtest configuration."""

    start_date: str
    end_date: str
    initial_capital: float = 1000000
    commission_rate: float = 0.001
    slippage_model: str = "fixed_bps"
    slippage_bps: int = 5


class BacktestRequest(BaseModel):
    """Request to run backtest."""

    strategy_id: str
    positions: List[Position]
    config: BacktestConfig


class PerformanceMetrics(BaseModel):
    """
    Performance metrics from Whaleforce API.

    IMPORTANT: All these values come from the API.
    DO NOT calculate them locally.
    """

    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_return: float
    annualized_volatility: float


class TradeStats(BaseModel):
    """Trade statistics from Whaleforce API."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    avg_holding_days: float
    trades_per_year: float


class Trade(BaseModel):
    """Individual trade result."""

    trade_id: str
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float = Field(..., alias="return")
    pnl: float


class BacktestResponse(BaseModel):
    """
    Backtest result from Whaleforce API.

    This is the SSOT for all performance metrics.
    """

    backtest_id: str
    strategy_id: str
    status: str
    performance: PerformanceMetrics
    trade_stats: TradeStats
    yearly_returns: Dict[str, float]
    trades: List[Trade]


class TradingDay(BaseModel):
    """Trading day information."""

    date: str
    is_trading_day: bool


class TradingCalendarResponse(BaseModel):
    """Trading calendar response."""

    trading_days: List[str]
    holidays: List[dict]


# =====================================
# Endpoints
# =====================================


@router.post("/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest) -> BacktestResponse:
    """
    Run backtest via Whaleforce API.

    IMPORTANT: All performance metrics (CAGR, Sharpe, win rate, etc.)
    are returned by the API. Do NOT calculate them locally.
    """
    client = get_backtest_client()

    # Convert positions to Whaleforce format
    wf_positions = [
        WFPosition(
            symbol=p.symbol,
            entry_date=p.entry_date,
            exit_date=p.exit_date,
            direction=p.direction,
            sizing=p.sizing,
            signal_id=p.signal_id,
            score=p.score,
        )
        for p in request.positions
    ]

    wf_config = WFBacktestConfig(
        start_date=request.config.start_date,
        end_date=request.config.end_date,
        initial_capital=request.config.initial_capital,
        commission_rate=request.config.commission_rate,
        slippage_model=request.config.slippage_model,
        slippage_bps=request.config.slippage_bps,
    )

    try:
        result = await client.run_backtest(
            strategy_id=request.strategy_id,
            positions=wf_positions,
            config=wf_config,
        )

        # Map response to API schema
        return BacktestResponse(
            backtest_id=result.backtest_id,
            strategy_id=result.strategy_id,
            status=result.status,
            performance=PerformanceMetrics(
                cagr=result.performance.cagr,
                sharpe_ratio=result.performance.sharpe_ratio,
                sortino_ratio=result.performance.sortino_ratio,
                max_drawdown=result.performance.max_drawdown,
                win_rate=result.performance.win_rate,
                profit_factor=result.performance.profit_factor,
                total_return=result.performance.total_return,
                annualized_volatility=result.performance.annualized_volatility,
            ),
            trade_stats=TradeStats(
                total_trades=result.trade_stats.total_trades,
                winning_trades=result.trade_stats.winning_trades,
                losing_trades=result.trade_stats.losing_trades,
                avg_win=result.trade_stats.avg_win,
                avg_loss=result.trade_stats.avg_loss,
                avg_holding_days=result.trade_stats.avg_holding_days,
                trades_per_year=result.trade_stats.trades_per_year,
            ),
            yearly_returns=result.yearly_returns,
            trades=[
                Trade(
                    trade_id=t.trade_id,
                    symbol=t.symbol,
                    entry_date=t.entry_date,
                    entry_price=t.entry_price,
                    exit_date=t.exit_date,
                    exit_price=t.exit_price,
                    **{"return": t.return_pct},
                    pnl=t.pnl,
                )
                for t in result.trades
            ],
        )

    except InvalidPositionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsufficientDataError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except APIConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Backtest API unavailable: {str(e)}")


@router.get("/trading-calendar", response_model=TradingCalendarResponse)
async def get_trading_calendar_endpoint(
    start_date: str,
    end_date: str,
) -> TradingCalendarResponse:
    """
    Get trading calendar.

    Returns list of trading days (excludes weekends and market holidays).
    Uses pandas_market_calendars for accurate NYSE calendar.
    """
    try:
        calendar = get_trading_calendar()
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        trading_days = calendar.get_trading_days_between(start, end)

        return TradingCalendarResponse(
            trading_days=[d.isoformat() for d in trading_days],
            holidays=[],  # Can be extended to list holidays if needed
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
