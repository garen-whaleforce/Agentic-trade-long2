"""
Trading Calendar Tests.

Tests for the SSOT trading calendar module.
"""

import pytest
from datetime import date

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from core.trading_calendar import (
    TradingCalendar,
    calculate_entry_date,
    calculate_exit_date,
    calculate_trading_dates,
    is_trading_day,
    next_trading_day,
    add_trading_days,
)


class TestTradingCalendar:
    """Test TradingCalendar class."""

    @pytest.fixture
    def calendar(self):
        """Create a trading calendar instance."""
        return TradingCalendar()

    def test_weekday_is_trading_day(self, calendar):
        """Regular weekday should be a trading day."""
        # January 2, 2024 was a Tuesday
        assert calendar.is_trading_day(date(2024, 1, 2)) is True

    def test_weekend_is_not_trading_day(self, calendar):
        """Weekend should not be a trading day."""
        # January 6, 2024 was a Saturday
        assert calendar.is_trading_day(date(2024, 1, 6)) is False
        # January 7, 2024 was a Sunday
        assert calendar.is_trading_day(date(2024, 1, 7)) is False

    def test_holiday_is_not_trading_day(self, calendar):
        """Market holiday should not be a trading day."""
        # January 1, 2024 was New Year's Day
        assert calendar.is_trading_day(date(2024, 1, 1)) is False
        # January 15, 2024 was MLK Day
        assert calendar.is_trading_day(date(2024, 1, 15)) is False

    def test_next_trading_day_from_weekday(self, calendar):
        """Next trading day from a weekday."""
        # From Tuesday to Wednesday
        assert calendar.next_trading_day(date(2024, 1, 2)) == date(2024, 1, 3)

    def test_next_trading_day_from_friday(self, calendar):
        """Next trading day from Friday should be Monday."""
        # January 5, 2024 was Friday
        # January 8, 2024 was Monday
        assert calendar.next_trading_day(date(2024, 1, 5)) == date(2024, 1, 8)

    def test_next_trading_day_over_holiday(self, calendar):
        """Next trading day should skip holidays."""
        # December 31, 2023 was Sunday, Jan 1 was holiday
        # Next trading day should be January 2, 2024
        assert calendar.next_trading_day(date(2023, 12, 31)) == date(2024, 1, 2)

    def test_add_trading_days(self, calendar):
        """Add N trading days."""
        # From January 2, 2024 (Tuesday), add 5 trading days
        # Should be January 9, 2024 (Tuesday)
        assert calendar.add_trading_days(date(2024, 1, 2), 5) == date(2024, 1, 9)

    def test_add_trading_days_over_weekend(self, calendar):
        """Add trading days that span a weekend."""
        # From Thursday Jan 4, add 3 trading days
        # Should skip weekend, land on Tuesday Jan 9
        assert calendar.add_trading_days(date(2024, 1, 4), 3) == date(2024, 1, 9)

    def test_add_trading_days_30(self, calendar):
        """Add 30 trading days (the holding period)."""
        # From January 2, 2024
        result = calendar.add_trading_days(date(2024, 1, 2), 30)
        # Should be approximately 6 weeks later (30 trading days)
        assert result > date(2024, 1, 2)
        # Count should be about 30 trading days
        trading_days = calendar.get_trading_days_between(
            date(2024, 1, 2), result
        )
        # First day is inclusive, so we should have 31 days
        assert len(trading_days) == 31


class TestEntryExitCalculation:
    """Test entry and exit date calculations."""

    def test_calculate_entry_date_weekday(self):
        """Entry date from a weekday event."""
        # Event on Tuesday Jan 2
        entry = calculate_entry_date(date(2024, 1, 2))
        # Entry should be Wednesday Jan 3
        assert entry == date(2024, 1, 3)

    def test_calculate_entry_date_friday(self):
        """Entry date from a Friday event."""
        # Event on Friday Jan 5
        entry = calculate_entry_date(date(2024, 1, 5))
        # Entry should be Monday Jan 8
        assert entry == date(2024, 1, 8)

    def test_calculate_exit_date_30_days(self):
        """Exit date should be T+30 trading days."""
        # Event on January 2, 2024
        exit_date = calculate_exit_date(date(2024, 1, 2), holding_days=30)

        # Verify it's approximately 30 trading days later
        calendar = TradingCalendar()
        entry = calculate_entry_date(date(2024, 1, 2))
        trading_days = calendar.count_trading_days(entry, exit_date)

        # Should be 29 trading days between entry and exit
        # (entry is day 1, exit is day 30)
        assert trading_days == 29

    def test_calculate_trading_dates_complete(self):
        """Test complete trading dates calculation."""
        result = calculate_trading_dates(date(2024, 1, 25))

        assert "t_day" in result
        assert "entry_date" in result
        assert "exit_date" in result
        assert "trading_days_between" in result

        assert result["t_day"] == date(2024, 1, 25)
        assert result["entry_date"] > result["t_day"]
        assert result["exit_date"] > result["entry_date"]


class TestEdgeCases:
    """Test edge cases for trading calendar."""

    def test_year_boundary(self):
        """Test date calculation across year boundary."""
        # Event near end of year
        result = calculate_trading_dates(date(2023, 12, 28))
        # Should handle year transition correctly
        assert result["entry_date"].year >= 2023
        assert result["exit_date"].year == 2024

    def test_thanksgiving_week(self):
        """Test during Thanksgiving (half day Friday)."""
        # Thanksgiving 2024 is November 28
        # Event on November 27 (Wednesday)
        entry = calculate_entry_date(date(2024, 11, 27))
        # Should be November 29 (Friday, half day but trading)
        assert entry == date(2024, 11, 29)

    def test_long_weekend_mlk(self):
        """Test MLK Day long weekend."""
        # MLK Day 2024 is January 15 (Monday)
        # Event on Friday January 12
        entry = calculate_entry_date(date(2024, 1, 12))
        # Should skip weekend and MLK Day, be January 16
        assert entry == date(2024, 1, 16)


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_is_trading_day(self):
        """Test is_trading_day function."""
        assert is_trading_day(date(2024, 1, 2)) is True
        assert is_trading_day(date(2024, 1, 6)) is False  # Saturday

    def test_next_trading_day(self):
        """Test next_trading_day function."""
        assert next_trading_day(date(2024, 1, 2)) == date(2024, 1, 3)

    def test_add_trading_days(self):
        """Test add_trading_days function."""
        result = add_trading_days(date(2024, 1, 2), 5)
        assert result == date(2024, 1, 9)
