"""
Pytest configuration and fixtures.
"""

import os
import sys
from datetime import date
from typing import Generator

import pytest

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def sample_event_date() -> date:
    """Sample event date for testing."""
    return date(2024, 1, 25)


@pytest.fixture
def sample_event_id() -> str:
    """Sample event ID for testing."""
    return "evt_aapl_2024q1"


@pytest.fixture
def sample_symbol() -> str:
    """Sample stock symbol for testing."""
    return "AAPL"


@pytest.fixture
def sample_transcript() -> dict:
    """Sample transcript data for testing."""
    return {
        "event_id": "evt_aapl_2024q1",
        "symbol": "AAPL",
        "company_name": "Apple Inc.",
        "fiscal_year": 2024,
        "fiscal_quarter": 1,
        "event_date": "2024-01-25",
        "sections": {
            "prepared_remarks": {
                "speakers": [
                    {
                        "name": "Tim Cook",
                        "role": "CEO",
                        "paragraphs": [
                            {"index": 0, "text": "Good afternoon everyone."},
                            {
                                "index": 1,
                                "text": "We're pleased to report strong results.",
                            },
                        ],
                    },
                    {
                        "name": "Luca Maestri",
                        "role": "CFO",
                        "paragraphs": [
                            {
                                "index": 0,
                                "text": "Revenue for the quarter was $119.6 billion.",
                            },
                        ],
                    },
                ]
            },
            "qa_session": {
                "exchanges": [
                    {
                        "analyst": "John Doe",
                        "firm": "Goldman Sachs",
                        "question": "Can you provide more color on services?",
                        "answers": [
                            {
                                "speaker": "Tim Cook",
                                "text": "Services continues to be a key driver.",
                            }
                        ],
                    }
                ]
            },
        },
    }


@pytest.fixture
def sample_batch_score_output() -> dict:
    """Sample batch_score output for testing."""
    return {
        "score": 0.82,
        "trade_candidate": True,
        "evidence_count": 3,
        "key_flags": {
            "guidance_positive": True,
            "revenue_beat": True,
            "margin_concern": False,
        },
        "evidence_snippets": [
            {
                "quote": "We expect 15-18% growth",
                "speaker": "CFO",
                "section": "prepared",
            },
            {
                "quote": "Pipeline is stronger than ever",
                "speaker": "CEO",
                "section": "qa",
            },
        ],
        "no_trade_reason": None,
    }
