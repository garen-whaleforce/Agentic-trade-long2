"""
Backtest endpoints.

All performance metrics come from Whaleforce Backtest API (SSOT).
Local calculation of CAGR, Sharpe, etc. is PROHIBITED.
"""

from datetime import date
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    # TODO: Implement actual API call to Whaleforce Backtest API
    # This is a stub response for now

    return BacktestResponse(
        backtest_id="bt_20260131_stub123",
        strategy_id=request.strategy_id,
        status="completed",
        performance=PerformanceMetrics(
            cagr=0.385,
            sharpe_ratio=2.15,
            sortino_ratio=2.85,
            max_drawdown=-0.153,
            win_rate=0.782,
            profit_factor=2.34,
            total_return=12.45,
            annualized_volatility=0.18,
        ),
        trade_stats=TradeStats(
            total_trades=847,
            winning_trades=662,
            losing_trades=185,
            avg_win=0.082,
            avg_loss=-0.045,
            avg_holding_days=30,
            trades_per_year=94,
        ),
        yearly_returns={
            "2017": 0.42,
            "2018": 0.28,
            "2019": 0.51,
            "2020": 0.38,
            "2021": 0.45,
            "2022": 0.22,
            "2023": 0.35,
            "2024": 0.41,
            "2025": 0.33,
        },
        trades=[
            Trade(
                trade_id="t_001",
                symbol="AAPL",
                entry_date="2024-01-26",
                entry_price=192.45,
                exit_date="2024-03-08",
                exit_price=215.30,
                **{"return": 0.1187},
                pnl=22850,
            ),
        ],
    )


@router.get("/trading-calendar", response_model=TradingCalendarResponse)
async def get_trading_calendar(
    start_date: str,
    end_date: str,
) -> TradingCalendarResponse:
    """
    Get trading calendar from Whaleforce API.

    Returns list of trading days (excludes weekends and market holidays).
    """
    # TODO: Implement actual API call to Whaleforce API
    # This is a stub response for now

    return TradingCalendarResponse(
        trading_days=[
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-08",
        ],
        holidays=[
            {"date": "2024-01-01", "name": "New Year's Day"},
            {"date": "2024-01-15", "name": "Martin Luther King Jr. Day"},
        ],
    )
