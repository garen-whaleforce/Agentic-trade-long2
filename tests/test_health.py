"""
Health endpoint tests.
"""

import pytest
from fastapi.testclient import TestClient

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app


client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_health_config():
    """Test health check returns configuration."""
    response = client.get("/health")
    data = response.json()
    assert "config" in data
    assert "llm_batch_score_model" in data["config"]
    assert "strategy_score_threshold" in data["config"]
