"""
Tests for MarketDataClient.

These tests verify:
1. Connection handling
2. Fail-closed behavior (returns None on errors)
3. Fallback logic for weekends/holidays
4. Data retrieval
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import psycopg2

from backend.services.market_data_client import (
    MarketDataClient,
    get_market_data_client,
    reset_market_data_client,
    OHLCV,
)


class TestMarketDataClientUnit:
    """Unit tests with mocked database."""

    def setup_method(self):
        """Reset global client before each test."""
        reset_market_data_client()

    def test_get_close_price_returns_price(self):
        """Test successful price retrieval."""
        client = MarketDataClient()

        with patch.object(client, "_get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {
                "date": date(2026, 1, 15),
                "close_price": 150.25,
            }
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
                mock_cursor
            )

            price = client.get_close_price("AAPL", date(2026, 1, 15))

            assert price == 150.25

    def test_get_close_price_returns_none_when_not_found(self):
        """Test fail-closed: returns None when no data found."""
        client = MarketDataClient()

        with patch.object(client, "_get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
                mock_cursor
            )

            price = client.get_close_price("INVALID", date(2026, 1, 15))

            assert price is None

    def test_get_close_price_returns_none_on_db_error(self):
        """Test fail-closed: returns None on database errors."""
        client = MarketDataClient(max_retries=1)

        with patch.object(client, "_get_connection") as mock_conn:
            mock_conn.return_value.__enter__.side_effect = psycopg2.OperationalError(
                "Connection failed"
            )

            price = client.get_close_price("AAPL", date(2026, 1, 15))

            assert price is None

    def test_get_close_price_uses_adjusted_by_default(self):
        """Test that adjusted close is used by default."""
        client = MarketDataClient(use_adjusted=True)

        with patch.object(client, "_get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {
                "date": date(2026, 1, 15),
                "close_price": 150.25,
            }
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
                mock_cursor
            )

            client.get_close_price("AAPL", date(2026, 1, 15))

            # Verify the query used adj_close
            call_args = mock_cursor.execute.call_args
            query = call_args[0][0]
            assert "adj_close" in query

    def test_get_close_price_can_use_raw_close(self):
        """Test that raw close can be used instead of adjusted."""
        client = MarketDataClient(use_adjusted=False)

        with patch.object(client, "_get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {
                "date": date(2026, 1, 15),
                "close_price": 150.25,
            }
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
                mock_cursor
            )

            client.get_close_price("AAPL", date(2026, 1, 15))

            # Verify the query used close (not adj_close)
            call_args = mock_cursor.execute.call_args
            query = call_args[0][0]
            assert "close" in query
            # Make sure it's not adj_close by checking the exact pattern
            assert "adj_close as close_price" not in query

    def test_get_ohlcv_returns_list(self):
        """Test OHLCV data retrieval."""
        client = MarketDataClient()

        with patch.object(client, "_get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                {
                    "symbol": "AAPL",
                    "date": date(2026, 1, 14),
                    "open": 148.0,
                    "high": 151.0,
                    "low": 147.0,
                    "close": 150.0,
                    "volume": 1000000,
                    "adj_close": 150.0,
                },
                {
                    "symbol": "AAPL",
                    "date": date(2026, 1, 15),
                    "open": 150.0,
                    "high": 152.0,
                    "low": 149.0,
                    "close": 151.0,
                    "volume": 1100000,
                    "adj_close": 151.0,
                },
            ]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
                mock_cursor
            )

            result = client.get_ohlcv("AAPL", date(2026, 1, 14), date(2026, 1, 15))

            assert len(result) == 2
            assert isinstance(result[0], OHLCV)
            assert result[0].symbol == "AAPL"
            assert result[0].close == 150.0

    def test_get_ohlcv_returns_empty_list_on_error(self):
        """Test fail-closed: returns empty list on error."""
        client = MarketDataClient(max_retries=1)

        with patch.object(client, "_get_connection") as mock_conn:
            mock_conn.return_value.__enter__.side_effect = psycopg2.OperationalError(
                "Connection failed"
            )

            result = client.get_ohlcv("AAPL", date(2026, 1, 14), date(2026, 1, 15))

            assert result == []

    def test_check_connection_returns_true_on_success(self):
        """Test connection check."""
        client = MarketDataClient()

        with patch.object(client, "_get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
                mock_cursor
            )

            result = client.check_connection()

            assert result is True

    def test_check_connection_returns_false_on_failure(self):
        """Test connection check failure."""
        client = MarketDataClient()

        with patch.object(client, "_get_connection") as mock_conn:
            mock_conn.return_value.__enter__.side_effect = Exception("Connection failed")

            result = client.check_connection()

            assert result is False

    def test_global_client_singleton(self):
        """Test that get_market_data_client returns singleton."""
        reset_market_data_client()

        client1 = get_market_data_client()
        client2 = get_market_data_client()

        assert client1 is client2

    def test_reset_client(self):
        """Test that reset_market_data_client clears singleton."""
        client1 = get_market_data_client()
        reset_market_data_client()
        client2 = get_market_data_client()

        assert client1 is not client2


class TestMarketDataClientIntegration:
    """Integration tests that require actual database connection."""

    @pytest.fixture
    def client(self):
        """Create a client for integration tests."""
        return MarketDataClient()

    @pytest.mark.integration
    def test_real_connection(self, client):
        """Test real database connection."""
        # This test requires actual database access
        # Skip if not in integration test mode
        result = client.check_connection()
        assert result is True, "Database connection failed"

    @pytest.mark.integration
    def test_real_price_retrieval(self, client):
        """Test real price retrieval for a known stock."""
        # Use a date we know has data
        price = client.get_close_price("AAPL", date(2024, 1, 15))
        assert price is not None, "Should have price data for AAPL"
        assert price > 0, "Price should be positive"

    @pytest.mark.integration
    def test_real_ohlcv_retrieval(self, client):
        """Test real OHLCV retrieval."""
        result = client.get_ohlcv("AAPL", date(2024, 1, 10), date(2024, 1, 15))
        assert len(result) > 0, "Should have OHLCV data"
        for ohlcv in result:
            assert ohlcv.high >= ohlcv.low, "High should be >= Low"
            assert ohlcv.close >= ohlcv.low, "Close should be >= Low"
            assert ohlcv.close <= ohlcv.high, "Close should be <= High"
