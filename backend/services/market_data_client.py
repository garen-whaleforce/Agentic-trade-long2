"""
Market Data Client.

Provides access to historical price data from PostgreSQL database.
Used by paper trading runner for entry/exit price lookups.

SSOT: This is the single source of truth for market data.
Fail-closed: Returns None or raises on any error - no guessing.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

from core.config import settings


logger = logging.getLogger("market_data_client")


class OHLCV(BaseModel):
    """OHLCV price data for a single day."""

    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None


class MarketDataClient:
    """
    Client for fetching market data from PostgreSQL.

    Principles:
    1. Fail-closed: Any error returns None or raises, never guesses
    2. Observability: All operations are logged
    3. Retry: Automatic retry on transient failures
    4. Consistency: Uses adjusted_close by default for corporate actions
    """

    # Default connection settings (fallback if settings not available)
    DEFAULT_HOST = "172.23.22.100"
    DEFAULT_PORT = 5432
    DEFAULT_DATABASE = "whaleforce"
    DEFAULT_USER = "whaleforce"
    DEFAULT_PASSWORD = "whaleforce.ai"

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        max_retries: int = 3,
        use_adjusted: bool = True,
    ):
        """
        Initialize market data client.

        Args:
            host: PostgreSQL host (default from settings)
            port: PostgreSQL port (default from settings)
            database: Database name (default from settings)
            user: Username (default from settings)
            password: Password (default from settings)
            max_retries: Max retry attempts on failure
            use_adjusted: Use adjusted_close (handles splits/dividends)
        """
        self.host = host or getattr(settings, "postgres_host", self.DEFAULT_HOST)
        self.port = port or getattr(settings, "postgres_port", self.DEFAULT_PORT)
        self.database = database or getattr(settings, "postgres_database", self.DEFAULT_DATABASE)
        self.user = user or getattr(settings, "postgres_user", self.DEFAULT_USER)
        self.password = password or getattr(settings, "postgres_password", self.DEFAULT_PASSWORD)
        self.max_retries = max_retries
        self.use_adjusted = use_adjusted

        self._conn = None

    @contextmanager
    def _get_connection(self):
        """Get a database connection with automatic cleanup."""
        conn = None
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=10,
            )
            yield conn
        except psycopg2.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def get_close_price(
        self,
        symbol: str,
        target_date: date,
        fallback_days: int = 5,
    ) -> Optional[float]:
        """
        Get closing price for a symbol on a specific date.

        If the exact date is not available (weekend/holiday), looks back
        up to fallback_days to find the most recent trading day.

        Fail-closed: Returns None if no price found within fallback window.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            target_date: Date to get price for
            fallback_days: Max days to look back for trading day

        Returns:
            Close price or None if not found
        """
        for attempt in range(self.max_retries):
            try:
                with self._get_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        # Look for price on target_date or most recent before it
                        start_date = target_date - timedelta(days=fallback_days)

                        # Determine which column to use
                        price_col = "adj_close" if self.use_adjusted else "close"

                        query = f"""
                            SELECT date, {price_col} as close_price
                            FROM historical_prices
                            WHERE symbol = %s
                              AND date <= %s
                              AND date >= %s
                            ORDER BY date DESC
                            LIMIT 1
                        """

                        cur.execute(query, (symbol.upper(), target_date, start_date))
                        row = cur.fetchone()

                        if row:
                            price = row["close_price"]
                            actual_date = row["date"]

                            if actual_date != target_date:
                                logger.info(
                                    f"No price for {symbol} on {target_date}, "
                                    f"using {actual_date} (fallback)"
                                )

                            logger.debug(
                                f"get_close_price({symbol}, {target_date}) = {price}"
                            )
                            return float(price)
                        else:
                            logger.warning(
                                f"No price found for {symbol} within "
                                f"{fallback_days} days of {target_date}"
                            )
                            return None

            except psycopg2.Error as e:
                logger.warning(
                    f"Database error on attempt {attempt + 1}/{self.max_retries}: {e}"
                )
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"Failed to get price for {symbol} after {self.max_retries} attempts"
                    )
                    return None

        return None

    def get_ohlcv(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> List[OHLCV]:
        """
        Get OHLCV data for a symbol in a date range.

        Args:
            symbol: Stock symbol
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of OHLCV records, empty list if error
        """
        for attempt in range(self.max_retries):
            try:
                with self._get_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        query = """
                            SELECT symbol, date, open, high, low, close, volume, adj_close
                            FROM historical_prices
                            WHERE symbol = %s
                              AND date >= %s
                              AND date <= %s
                            ORDER BY date ASC
                        """

                        cur.execute(query, (symbol.upper(), start_date, end_date))
                        rows = cur.fetchall()

                        results = []
                        for row in rows:
                            results.append(
                                OHLCV(
                                    symbol=row["symbol"],
                                    date=row["date"],
                                    open=float(row["open"]),
                                    high=float(row["high"]),
                                    low=float(row["low"]),
                                    close=float(row["close"]),
                                    volume=int(row["volume"]),
                                    adjusted_close=float(row["adj_close"])
                                    if row["adj_close"]
                                    else None,
                                )
                            )

                        logger.debug(
                            f"get_ohlcv({symbol}, {start_date}, {end_date}) "
                            f"returned {len(results)} records"
                        )
                        return results

            except psycopg2.Error as e:
                logger.warning(
                    f"Database error on attempt {attempt + 1}/{self.max_retries}: {e}"
                )
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"Failed to get OHLCV for {symbol} after {self.max_retries} attempts"
                    )
                    return []

        return []

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the most recent closing price for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Most recent close price or None
        """
        return self.get_close_price(symbol, date.today(), fallback_days=10)

    def check_connection(self) -> bool:
        """
        Check if database connection is working.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False


# Global instance
_client: Optional[MarketDataClient] = None


def get_market_data_client() -> MarketDataClient:
    """Get the global market data client instance."""
    global _client
    if _client is None:
        _client = MarketDataClient()
    return _client


def reset_market_data_client() -> None:
    """Reset the global client (for testing)."""
    global _client
    _client = None
