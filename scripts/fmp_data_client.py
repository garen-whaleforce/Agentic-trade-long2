#!/usr/bin/env python3
"""
FMP (Financial Modeling Prep) Data Client — Stable API.

Provides the same data interface as the PostgreSQL DB queries in daily_signal_v9.py,
but sources data from the FMP stable API. This enables 2026+ live paper trading
when the DB is not yet updated.

Usage:
    from fmp_data_client import FMPDataClient

    client = FMPDataClient(api_key="...")
    events = client.query_day_events("2026-01-28")
    spy_prices = client.load_spy_prices()
    vix_prices = client.load_vix_prices()
"""

import os
import time
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FMPDataClient:
    """FMP Stable API data client, drop-in replacement for DB queries."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("FMP_API_KEY", "")
        if not self.api_key:
            raise ValueError("FMP_API_KEY not set. Pass api_key or set env var.")
        self.session = requests.Session()
        self.session.verify = False
        # Cache for prices (avoid re-fetching)
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._sector_cache: Dict[str, str] = {}
        # Cache for sector features by date (avoid redundant computation)
        self._sector_features_cache: Dict[str, dict] = {}  # "sector_date" -> features

    def _get(self, endpoint: str, params: Optional[dict] = None) -> list:
        """Make GET request to FMP stable API."""
        url = f"{FMP_BASE_URL}/{endpoint}"
        p = {"apikey": self.api_key}
        if params:
            p.update(params)
        resp = self.session.get(url, params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            raise ValueError(f"FMP API error: {data['Error Message']}")
        return data if isinstance(data, list) else [data] if data else []

    # ── Earnings ──────────────────────────────────────────────────────

    def query_earnings_calendar(self, date_from: str, date_to: str) -> List[dict]:
        """Query earnings calendar for a date range."""
        return self._get("earnings-calendar", {"from": date_from, "to": date_to})

    def _load_sp500_symbols(self) -> set:
        """Load S&P 500 constituent symbols (cached)."""
        if not hasattr(self, '_sp500_symbols') or not self._sp500_symbols:
            data = self._get("sp500-constituent")
            self._sp500_symbols = {row.get("symbol") for row in data if row.get("symbol")}
            # Also cache sectors
            for row in data:
                sym = row.get("symbol")
                sec = row.get("sector", "Unknown")
                if sym:
                    self._sector_cache[sym] = sec
        return self._sp500_symbols

    def query_day_events(self, target_date: str) -> List[dict]:
        """
        Query earnings events on target_date with drop >= 5%.

        Mirrors the DB query in daily_signal_v9.py:query_day_events().
        Returns list of dicts with keys matching the DB output.
        Only includes S&P 500 constituents (matching DB behavior).
        """
        # Load S&P 500 universe
        sp500 = self._load_sp500_symbols()

        # Get earnings for target date (expand window by 1 day for timezone edge cases)
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        date_from = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

        earnings = self.query_earnings_calendar(date_from, date_to)

        # Filter to exact date, valid EPS, and S&P 500 only
        day_earnings = []
        for e in earnings:
            if e.get("date") != target_date:
                continue
            if e.get("symbol") not in sp500:
                continue
            eps_actual = e.get("epsActual")
            eps_estimated = e.get("epsEstimated")
            if eps_actual is None or eps_estimated is None:
                continue
            day_earnings.append(e)

        if not day_earnings:
            return []

        # Get prices for each symbol and check for >= 5% drop
        events = []
        for e in day_earnings:
            symbol = e["symbol"]
            eps_actual = float(e["epsActual"])
            eps_estimated = float(e["epsEstimated"])

            # EPS surprise
            if eps_estimated != 0:
                eps_surprise = (eps_actual - eps_estimated) / abs(eps_estimated)
            else:
                eps_surprise = 0.0

            # Get sector
            sector = self._get_sector(symbol)

            # Get prices around event date
            prices = self._get_symbol_prices(symbol, target_date, lookback_days=5, forward_days=5)
            if not prices:
                continue

            sorted_dates = sorted(prices.keys())

            # price_t0: last close on or before event_date
            price_t0 = None
            t0_date = None
            for d in sorted_dates:
                if d <= target_date:
                    price_t0 = prices[d]
                    t0_date = d

            # price_t1: first close after event_date
            price_t1 = None
            t1_date = None
            for d in sorted_dates:
                if d > target_date:
                    price_t1 = prices[d]
                    t1_date = d
                    break

            if price_t0 is None or price_t1 is None or price_t0 == 0:
                continue

            drop_1d = (price_t1 - price_t0) / price_t0
            if drop_1d > -0.05:
                continue  # Not a >= 5% drop

            events.append({
                "symbol": symbol,
                "company_name": e.get("companyName", symbol),
                "sector": sector,
                "event_date": target_date,
                "eps_actual": eps_actual,
                "eps_estimated": eps_estimated,
                "eps_surprise": eps_surprise,
                "price_t0": price_t0,
                "price_t1": price_t1,
                "t1_date": t1_date,
                "drop_1d": drop_1d,
            })

        events.sort(key=lambda x: x["symbol"])
        return events

    # ── Prices ────────────────────────────────────────────────────────

    def _get_symbol_prices(
        self, symbol: str, around_date: str,
        lookback_days: int = 5, forward_days: int = 5
    ) -> Dict[str, float]:
        """Get close prices around a date for a single symbol."""
        dt = datetime.strptime(around_date, "%Y-%m-%d")
        date_from = (dt - timedelta(days=lookback_days + 5)).strftime("%Y-%m-%d")
        date_to = (dt + timedelta(days=forward_days + 5)).strftime("%Y-%m-%d")

        cache_key = f"{symbol}_{date_from}_{date_to}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        data = self._get("historical-price-eod/full", {
            "symbol": symbol, "from": date_from, "to": date_to
        })

        prices = {}
        for row in data:
            d = row.get("date")
            c = row.get("close")
            if d and c is not None:
                prices[d] = float(c)

        self._price_cache[cache_key] = prices
        return prices

    def load_full_prices(self, symbol: str, from_date: str = "2016-01-01") -> Dict[str, float]:
        """Load all close prices for a symbol from from_date to today."""
        cache_key = f"{symbol}_full_{from_date}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        data = self._get("historical-price-eod/full", {
            "symbol": symbol, "from": from_date
        })

        prices = {}
        for row in data:
            d = row.get("date")
            c = row.get("close")
            if d and c is not None:
                prices[d] = float(c)

        self._price_cache[cache_key] = prices
        return prices

    def load_ohlcv_prices(self, symbol: str, from_date: str = "2016-01-01") -> Dict[str, dict]:
        """
        Load OHLCV prices for a symbol. Returns {date: {open, high, low, close, volume}}.
        Used for V10 candle features (gap_pct, intraday_ret, close_pos, etc.).
        """
        cache_key = f"{symbol}_ohlcv_{from_date}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        data = self._get("historical-price-eod/full", {
            "symbol": symbol, "from": from_date
        })

        ohlcv = {}
        for row in data:
            d = row.get("date")
            if d and row.get("close") is not None:
                ohlcv[d] = {
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
                }

        self._price_cache[cache_key] = ohlcv
        return ohlcv

    def load_spy_prices(self, from_date: str = "2016-01-01") -> Dict[str, float]:
        """Load SPY close prices for 200DMA and bear duration."""
        return self.load_full_prices("SPY", from_date)

    def load_vix_prices(self, from_date: str = "2016-01-01") -> Dict[str, float]:
        """Load VIX close prices for percentile calculation."""
        # FMP uses ^VIX (URL-encoded as %5EVIX)
        return self.load_full_prices("^VIX", from_date)

    # ── Sector ────────────────────────────────────────────────────────

    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol via company profile."""
        if symbol in self._sector_cache:
            return self._sector_cache[symbol]

        try:
            data = self._get("profile", {"symbol": symbol})
            if data and isinstance(data, list) and len(data) > 0:
                sector = data[0].get("sector", "Unknown") or "Unknown"
            else:
                sector = "Unknown"
        except Exception:
            sector = "Unknown"

        self._sector_cache[symbol] = sector
        return sector

    def load_sp500_sectors(self) -> Dict[str, str]:
        """Load all S&P 500 constituents with sectors."""
        data = self._get("sp500-constituent")
        sectors = {}
        for row in data:
            symbol = row.get("symbol")
            sector = row.get("sector", "Unknown")
            if symbol:
                sectors[symbol] = sector
                self._sector_cache[symbol] = sector
        return sectors

    # ── Sector Momentum (simplified) ──────────────────────────────────

    def compute_sector_features(self, symbol: str, event_date: str) -> dict:
        """
        Compute sector momentum features using FMP data.

        Uses ALL same-sector S&P 500 stocks (matching DB behavior).
        Prices are cached per-symbol to avoid redundant API calls.
        Results cached per sector+date to avoid recomputing for same-day events.
        """
        sector = self._get_sector(symbol)
        if sector == "Unknown":
            return {"sector_return_20d": 0.0, "sector_breadth": 0.5}

        # Check sector+date cache first
        cache_key = f"{sector}_{event_date}"
        if cache_key in self._sector_features_cache:
            return self._sector_features_cache[cache_key]

        # Load S&P 500 sectors if not cached
        if len(self._sector_cache) < 100:
            self.load_sp500_sectors()

        # Get ALL same-sector symbols (no sampling — matches DB calculation)
        sector_symbols = [s for s, sec in self._sector_cache.items() if sec == sector]
        if not sector_symbols:
            return {"sector_return_20d": 0.0, "sector_breadth": 0.5}

        returns_20d = []
        for sym in sector_symbols:
            try:
                prices = self._get_symbol_prices(sym, event_date, lookback_days=40, forward_days=0)
                if not prices:
                    continue
                sorted_dates = sorted(prices.keys())
                # Find dates on or before event_date
                valid = [d for d in sorted_dates if d <= event_date]
                if len(valid) < 20:
                    continue
                p_now = prices[valid[-1]]
                p_20 = prices[valid[-20]]
                if p_20 > 0:
                    ret = (p_now - p_20) / p_20
                    returns_20d.append(ret)
            except Exception:
                continue

        if not returns_20d:
            return {"sector_return_20d": 0.0, "sector_breadth": 0.5}

        sector_return = sum(returns_20d) / len(returns_20d)
        breadth = sum(1 for r in returns_20d if r > 0) / len(returns_20d)

        result = {
            "sector_return_20d": round(sector_return, 5),
            "sector_breadth": round(breadth, 3),
        }
        self._sector_features_cache[cache_key] = result
        return result
