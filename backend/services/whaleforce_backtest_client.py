"""
Whaleforce Backtest API Client.

This is the SSOT (Single Source of Truth) for all performance metrics.

CRITICAL: Do NOT calculate CAGR, Sharpe, Win Rate, or any performance
metrics locally. ALL performance numbers must come from this API.
"""

from datetime import date
from typing import List, Optional, Dict, Any

import httpx
from pydantic import BaseModel

from core.config import settings


# =====================================
# Request Models
# =====================================


class Position(BaseModel):
    """Trading position for backtest."""

    symbol: str
    entry_date: str  # T+1 close
    exit_date: str  # T+30 close
    direction: str = "long"
    sizing: str = "equal_weight"
    signal_id: str
    score: float


class BacktestConfig(BaseModel):
    """Configuration for backtest."""

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


# =====================================
# Response Models
# =====================================


class PerformanceMetrics(BaseModel):
    """
    Performance metrics from backtest.

    IMPORTANT: All values come from API. Never calculate locally.
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
    """Trade statistics from backtest."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    avg_holding_days: float
    trades_per_year: float


class Trade(BaseModel):
    """Individual trade from backtest."""

    trade_id: str
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float
    pnl: float


class BacktestResult(BaseModel):
    """Result from backtest API."""

    backtest_id: str
    strategy_id: str
    status: str
    performance: PerformanceMetrics
    trade_stats: TradeStats
    yearly_returns: Dict[str, float]
    trades: List[Trade]


class TradingCalendarResponse(BaseModel):
    """Trading calendar from API."""

    trading_days: List[str]
    holidays: List[Dict[str, str]]


# =====================================
# Exceptions
# =====================================


class BacktestAPIError(Exception):
    """Base exception for backtest API errors."""

    pass


class InvalidPositionError(BacktestAPIError):
    """Invalid position data."""

    pass


class InsufficientDataError(BacktestAPIError):
    """Missing price data for backtest."""

    pass


class APIConnectionError(BacktestAPIError):
    """API connection error."""

    pass


# =====================================
# Client
# =====================================


class WhaleforceBacktestClient:
    """
    Client for Whaleforce Backtest API.

    IMPORTANT: This is the SSOT for all performance metrics.
    Never calculate CAGR, Sharpe, or Win Rate locally.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the client.

        Args:
            api_key: API key for authentication
            base_url: Base URL for the API
        """
        self.api_key = api_key or settings.whaleforce_backtest_api_key
        self.base_url = base_url or settings.whaleforce_backtest_api_url

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120.0,  # Backtests can take time
        )

        # Cache for trading calendar
        self._calendar_cache: Optional[TradingCalendarResponse] = None

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def run_backtest(
        self,
        strategy_id: str,
        positions: List[Position],
        config: BacktestConfig,
    ) -> BacktestResult:
        """
        Run backtest via API.

        Args:
            strategy_id: Strategy identifier
            positions: List of trading positions
            config: Backtest configuration

        Returns:
            BacktestResult with performance metrics from API
        """
        request = BacktestRequest(
            strategy_id=strategy_id,
            positions=positions,
            config=config,
        )

        try:
            response = await self._client.post(
                "/backtest",
                json=request.model_dump(),
            )
            response.raise_for_status()
            data = response.json()

            return BacktestResult(**data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                raise InvalidPositionError(f"Invalid positions: {e.response.text}")
            if e.response.status_code == 422:
                raise InsufficientDataError(f"Missing price data: {e.response.text}")
            raise APIConnectionError(f"API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIConnectionError(f"Connection error: {str(e)}")

    async def get_trading_calendar(
        self,
        start_date: date,
        end_date: date,
        use_cache: bool = True,
    ) -> TradingCalendarResponse:
        """
        Get trading calendar from API.

        Args:
            start_date: Start date
            end_date: End date
            use_cache: Whether to use cached calendar

        Returns:
            TradingCalendarResponse with trading days
        """
        if use_cache and self._calendar_cache is not None:
            return self._calendar_cache

        try:
            response = await self._client.get(
                "/trading-calendar",
                params={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()

            result = TradingCalendarResponse(**data)

            if use_cache:
                self._calendar_cache = result

            return result

        except httpx.HTTPStatusError as e:
            raise APIConnectionError(f"API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIConnectionError(f"Connection error: {str(e)}")


# =====================================
# Convenience Functions
# =====================================


_client: Optional[WhaleforceBacktestClient] = None


def get_backtest_client() -> WhaleforceBacktestClient:
    """Get the singleton backtest client."""
    global _client
    if _client is None:
        _client = WhaleforceBacktestClient()
    return _client


async def run_backtest(
    strategy_id: str,
    positions: List[Position],
    start_date: str,
    end_date: str,
) -> BacktestResult:
    """
    Convenience function to run backtest.

    Args:
        strategy_id: Strategy identifier
        positions: List of positions
        start_date: Start date string
        end_date: End date string

    Returns:
        BacktestResult from API
    """
    client = get_backtest_client()

    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
    )

    return await client.run_backtest(strategy_id, positions, config)
