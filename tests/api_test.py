"""Smoke tests for Contrarian Alpha Paper Trading Dashboard."""

import requests
import pytest


class TestHealthEndpoints:
    """Backend API smoke tests — must all pass for deploy."""

    def test_health(self, service_url):
        r = requests.get(f"{service_url}/health", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_paper_trading_health(self, service_url):
        r = requests.get(f"{service_url}/api/paper-trading/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "positions_file_exists" in data
        assert "config_file_exists" in data
        assert "signal_days" in data

    def test_summary(self, service_url):
        r = requests.get(f"{service_url}/api/paper-trading/summary", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "open_count" in data
        assert "closed_count" in data
        assert "total_positions" in data

    def test_positions(self, service_url):
        r = requests.get(f"{service_url}/api/paper-trading/positions", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "open" in data
        assert "closed" in data

    def test_signal_dates(self, service_url):
        r = requests.get(
            f"{service_url}/api/paper-trading/signals/dates", timeout=10
        )
        assert r.status_code == 200
        data = r.json()
        assert "dates" in data
        assert isinstance(data["dates"], list)


class TestFrontendEndpoints:
    """Frontend smoke tests — verify Next.js is serving pages."""

    def test_dashboard_page(self, frontend_url):
        r = requests.get(f"{frontend_url}/dashboard", timeout=15)
        assert r.status_code == 200
        assert "html" in r.headers.get("content-type", "").lower()
