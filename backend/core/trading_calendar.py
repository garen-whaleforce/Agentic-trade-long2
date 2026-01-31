"""
Trading Calendar Module - SSOT for all date calculations.

This module is the Single Source of Truth for:
- T day (earnings call publish date)
- Entry date (T+1 trading day close)
- Exit date (T+30 trading day close)

IMPORTANT: All date calculations in the system MUST go through this module.
Do NOT calculate trading days elsewhere.
"""

from datetime import date, timedelta
from typing import List, Optional, Set
from functools import lru_cache

import pandas_market_calendars as mcal


class TradingCalendar:
    """
    US Stock Market Trading Calendar.

    Provides methods to:
    - Check if a date is a trading day
    - Get the next trading day
    - Add N trading days to a date
    - Calculate entry and exit dates for earnings events
    """

    def __init__(self, exchange: str = "NYSE"):
        """
        Initialize the trading calendar.

        Args:
            exchange: Exchange name (default: NYSE)
        """
        self.exchange = exchange
        self._calendar = mcal.get_calendar(exchange)
        self._trading_days_cache: Set[date] = set()
        self._cache_start: Optional[date] = None
        self._cache_end: Optional[date] = None

    def _ensure_cache(self, start: date, end: date) -> None:
        """Ensure the cache covers the required date range."""
        # Extend range for safety
        cache_start = start - timedelta(days=30)
        cache_end = end + timedelta(days=60)

        # Check if we need to refresh cache
        if (
            self._cache_start is None
            or self._cache_end is None
            or cache_start < self._cache_start
            or cache_end > self._cache_end
        ):
            # Get trading days for the range
            schedule = self._calendar.schedule(
                start_date=cache_start.isoformat(),
                end_date=cache_end.isoformat(),
            )
            self._trading_days_cache = set(
                d.date() for d in schedule.index.to_pydatetime()
            )
            self._cache_start = cache_start
            self._cache_end = cache_end

    def is_trading_day(self, d: date) -> bool:
        """
        Check if a date is a trading day.

        Args:
            d: Date to check

        Returns:
            True if the date is a trading day
        """
        self._ensure_cache(d, d)
        return d in self._trading_days_cache

    def next_trading_day(self, d: date) -> date:
        """
        Get the next trading day after a given date.

        This is used to calculate T+1 (entry date).

        Args:
            d: Reference date (T day)

        Returns:
            The next trading day after d
        """
        self._ensure_cache(d, d + timedelta(days=10))
        next_day = d + timedelta(days=1)

        # Find the next trading day
        while next_day not in self._trading_days_cache:
            next_day += timedelta(days=1)
            # Safety check
            if next_day > d + timedelta(days=30):
                raise ValueError(f"No trading day found within 30 days of {d}")

        return next_day

    def add_trading_days(self, d: date, n: int) -> date:
        """
        Add N trading days to a date.

        This is used to calculate T+30 (exit date).

        Args:
            d: Start date
            n: Number of trading days to add

        Returns:
            The date that is N trading days after d
        """
        if n <= 0:
            raise ValueError(f"n must be positive, got {n}")

        self._ensure_cache(d, d + timedelta(days=n * 2))

        # Get sorted trading days after d
        future_trading_days = sorted(
            [td for td in self._trading_days_cache if td > d]
        )

        if len(future_trading_days) < n:
            raise ValueError(f"Not enough trading days in cache after {d}")

        return future_trading_days[n - 1]

    def get_trading_days_between(self, start: date, end: date) -> List[date]:
        """
        Get all trading days between two dates (inclusive).

        Args:
            start: Start date
            end: End date

        Returns:
            List of trading days
        """
        self._ensure_cache(start, end)
        return sorted([d for d in self._trading_days_cache if start <= d <= end])

    def count_trading_days(self, start: date, end: date) -> int:
        """
        Count trading days between two dates (exclusive of start, inclusive of end).

        Args:
            start: Start date (not counted)
            end: End date (counted if trading day)

        Returns:
            Number of trading days
        """
        return len(self.get_trading_days_between(start + timedelta(days=1), end))

    def calculate_entry_date(self, event_date: date) -> date:
        """
        Calculate entry date (T+1 trading day close).

        Args:
            event_date: T day (earnings call publish date)

        Returns:
            Entry date (T+1 close)
        """
        return self.next_trading_day(event_date)

    def calculate_exit_date(self, event_date: date, holding_days: int = 30) -> date:
        """
        Calculate exit date (T+N trading day close).

        Args:
            event_date: T day (earnings call publish date)
            holding_days: Number of trading days to hold (default: 30)

        Returns:
            Exit date (T+30 close by default)
        """
        entry_date = self.calculate_entry_date(event_date)
        # Exit is 30 trading days after entry
        # So we add 29 more trading days from entry (entry is day 1)
        return self.add_trading_days(entry_date, holding_days - 1)

    def calculate_trading_dates(
        self,
        event_date: date,
        holding_days: int = 30,
    ) -> dict:
        """
        Calculate all trading dates for an earnings event.

        This is the main method for getting SSOT dates.

        Args:
            event_date: T day (earnings call publish date)
            holding_days: Number of trading days to hold (default: 30)

        Returns:
            Dictionary with t_day, entry_date, exit_date, and trading_days_between
        """
        entry_date = self.calculate_entry_date(event_date)
        exit_date = self.calculate_exit_date(event_date, holding_days)
        trading_days = self.count_trading_days(entry_date, exit_date)

        return {
            "t_day": event_date,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "trading_days_between": trading_days,
        }


# Global instance for convenience
_default_calendar: Optional[TradingCalendar] = None


def get_trading_calendar() -> TradingCalendar:
    """Get the default trading calendar instance."""
    global _default_calendar
    if _default_calendar is None:
        _default_calendar = TradingCalendar()
    return _default_calendar


# Convenience functions using default calendar


def is_trading_day(d: date) -> bool:
    """Check if a date is a trading day."""
    return get_trading_calendar().is_trading_day(d)


def next_trading_day(d: date) -> date:
    """Get the next trading day after a date."""
    return get_trading_calendar().next_trading_day(d)


def add_trading_days(d: date, n: int) -> date:
    """Add N trading days to a date."""
    return get_trading_calendar().add_trading_days(d, n)


def calculate_entry_date(event_date: date) -> date:
    """Calculate entry date (T+1 close)."""
    return get_trading_calendar().calculate_entry_date(event_date)


def calculate_exit_date(event_date: date, holding_days: int = 30) -> date:
    """Calculate exit date (T+30 close by default)."""
    return get_trading_calendar().calculate_exit_date(event_date, holding_days)


def calculate_trading_dates(event_date: date, holding_days: int = 30) -> dict:
    """Calculate all trading dates for an event."""
    return get_trading_calendar().calculate_trading_dates(event_date, holding_days)
