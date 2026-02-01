"""
Regression Test Fixtures.

Fixed test data for regression testing.
These fixtures ensure reproducible tests across different runs.

IMPORTANT: These fixtures are FROZEN and should not be modified
without explicit decision record in docs/decisions/.
"""

import json
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional

from pydantic import BaseModel


class EventFixture(BaseModel):
    """A fixed earnings call event for testing."""

    event_id: str
    symbol: str
    company_name: str
    fiscal_year: int
    fiscal_quarter: int
    event_date: str

    # Expected dates (for calendar tests)
    expected_entry_date: str
    expected_exit_date: str

    # Transcript excerpt (for LLM tests)
    transcript_excerpt: str

    # Expected analysis results (golden output)
    expected_score_range: tuple[float, float]  # (min, max)
    expected_trade_decision: bool
    expected_key_flags: Dict[str, bool]

    # Metadata
    category: str  # "positive", "negative", "edge_case"
    notes: Optional[str] = None


# ============================================
# Fixed Test Events
# ============================================

REGRESSION_EVENTS: List[EventFixture] = [
    # ---- POSITIVE CASES (should trigger LONG) ----
    EventFixture(
        event_id="test_pos_001",
        symbol="AAPL",
        company_name="Apple Inc.",
        fiscal_year=2024,
        fiscal_quarter=1,
        event_date="2024-01-25",
        expected_entry_date="2024-01-26",
        expected_exit_date="2024-03-08",
        transcript_excerpt="""
        Tim Cook, CEO: We are incredibly pleased to report record revenue of $119.6 billion,
        up 2% year-over-year. iPhone revenue came in at $69.7 billion, also a record.

        Luca Maestri, CFO: We're raising our guidance for the March quarter.
        We expect revenue between $90 and $94 billion, representing growth of 4-8%.
        Gross margin is expected to be between 46% and 47%.

        Analyst: Can you talk about the trajectory of services revenue?
        Tim Cook: Services had a phenomenal quarter, reaching an all-time record of $23.1 billion.
        We see strong momentum continuing into the next quarter.
        """,
        expected_score_range=(0.70, 0.95),
        expected_trade_decision=True,
        expected_key_flags={
            "guidance_positive": True,
            "revenue_beat": True,
            "margin_concern": False,
        },
        category="positive",
        notes="Strong beat + raised guidance",
    ),
    EventFixture(
        event_id="test_pos_002",
        symbol="MSFT",
        company_name="Microsoft Corporation",
        fiscal_year=2024,
        fiscal_quarter=2,
        event_date="2024-01-30",
        expected_entry_date="2024-01-31",
        expected_exit_date="2024-03-14",
        transcript_excerpt="""
        Satya Nadella, CEO: This was a standout quarter with revenue of $62 billion,
        up 18% year-over-year. Azure and cloud services grew 30%.

        Amy Hood, CFO: For Q3, we expect revenue of $60-61 billion, representing
        approximately 15% growth. Operating margins should expand by 100 basis points.

        Analyst: How is AI demand impacting Azure growth?
        Satya Nadella: AI services contributed 6 percentage points to Azure growth.
        We're seeing unprecedented enterprise adoption of our Copilot products.
        """,
        expected_score_range=(0.75, 0.95),
        expected_trade_decision=True,
        expected_key_flags={
            "guidance_positive": True,
            "revenue_beat": True,
            "margin_concern": False,
        },
        category="positive",
        notes="Strong cloud growth + AI momentum",
    ),
    # ---- NEGATIVE CASES (should NOT trigger LONG) ----
    EventFixture(
        event_id="test_neg_001",
        symbol="XYZ",
        company_name="XYZ Corp",
        fiscal_year=2024,
        fiscal_quarter=1,
        event_date="2024-02-15",
        expected_entry_date="2024-02-16",
        expected_exit_date="2024-03-29",
        transcript_excerpt="""
        CEO: We faced significant headwinds this quarter. Revenue declined 8% to $2.1 billion,
        below our guidance of $2.3-2.4 billion.

        CFO: We are lowering our full-year guidance. We now expect revenue of $8-8.5 billion,
        down from our previous guidance of $9.5 billion. Gross margins compressed by 200 basis
        points due to increased input costs.

        Analyst: What's driving the margin compression?
        CFO: We're seeing persistent cost inflation in raw materials and labor.
        We don't expect relief until the second half of the year.
        """,
        expected_score_range=(0.20, 0.45),
        expected_trade_decision=False,
        expected_key_flags={
            "guidance_positive": False,
            "revenue_beat": False,
            "margin_concern": True,
        },
        category="negative",
        notes="Revenue miss + lowered guidance + margin compression",
    ),
    EventFixture(
        event_id="test_neg_002",
        symbol="ABC",
        company_name="ABC Industries",
        fiscal_year=2024,
        fiscal_quarter=1,
        event_date="2024-02-20",
        expected_entry_date="2024-02-21",
        expected_exit_date="2024-04-04",
        transcript_excerpt="""
        CEO: Revenue was flat at $1.5 billion, in line with expectations.

        CFO: We are maintaining our guidance for the year.
        No changes to our previous outlook.

        Analyst: Can you provide more color on the demand environment?
        CEO: The market remains challenging. We're focused on cost control.
        """,
        expected_score_range=(0.35, 0.55),
        expected_trade_decision=False,
        expected_key_flags={
            "guidance_positive": False,
            "revenue_beat": False,
            "margin_concern": False,
        },
        category="negative",
        notes="Flat results, no catalysts, insufficient evidence for LONG",
    ),
    # ---- EDGE CASES ----
    EventFixture(
        event_id="test_edge_001",
        symbol="EDGE",
        company_name="Edge Case Corp",
        fiscal_year=2024,
        fiscal_quarter=1,
        event_date="2024-01-12",  # Friday before MLK Day
        expected_entry_date="2024-01-16",  # Tuesday (skip weekend + MLK)
        expected_exit_date="2024-02-29",  # Leap year
        transcript_excerpt="""
        CEO: Strong quarter with 12% revenue growth to $500 million.

        CFO: We expect continued momentum. Guidance for next quarter is $520-540 million.
        """,
        expected_score_range=(0.60, 0.80),
        expected_trade_decision=True,
        expected_key_flags={
            "guidance_positive": True,
            "revenue_beat": True,
            "margin_concern": False,
        },
        category="edge_case",
        notes="Holiday weekend + leap year calendar edge case",
    ),
    EventFixture(
        event_id="test_edge_002",
        symbol="THIN",
        company_name="Thin Transcript Inc",
        fiscal_year=2024,
        fiscal_quarter=1,
        event_date="2024-03-01",
        expected_entry_date="2024-03-04",
        expected_exit_date="2024-04-16",
        transcript_excerpt="""
        CEO: Good quarter. Revenue up 5%.
        """,
        expected_score_range=(0.30, 0.50),
        expected_trade_decision=False,
        expected_key_flags={
            "guidance_positive": False,
            "revenue_beat": True,
            "margin_concern": False,
        },
        category="edge_case",
        notes="Insufficient transcript content - should abstain due to lack of evidence",
    ),
]


class FixtureLoader:
    """Loads and manages test fixtures."""

    def __init__(self, fixtures_dir: Optional[Path] = None):
        """
        Initialize the loader.

        Args:
            fixtures_dir: Directory containing fixture files
        """
        self.fixtures_dir = fixtures_dir or Path("tests/fixtures")
        self._events: Dict[str, EventFixture] = {}

        # Load built-in fixtures
        for event in REGRESSION_EVENTS:
            self._events[event.event_id] = event

    def get_event(self, event_id: str) -> Optional[EventFixture]:
        """Get a specific event by ID."""
        return self._events.get(event_id)

    def get_all_events(self) -> List[EventFixture]:
        """Get all events."""
        return list(self._events.values())

    def get_events_by_category(self, category: str) -> List[EventFixture]:
        """Get events by category."""
        return [e for e in self._events.values() if e.category == category]

    def get_positive_events(self) -> List[EventFixture]:
        """Get all positive (should trade) events."""
        return self.get_events_by_category("positive")

    def get_negative_events(self) -> List[EventFixture]:
        """Get all negative (should not trade) events."""
        return self.get_events_by_category("negative")

    def get_edge_cases(self) -> List[EventFixture]:
        """Get all edge case events."""
        return self.get_events_by_category("edge_case")

    def save_fixtures(self, filepath: Path) -> None:
        """Save fixtures to JSON file."""
        data = [e.model_dump() for e in self._events.values()]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def load_fixtures(self, filepath: Path) -> None:
        """Load fixtures from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        for item in data:
            event = EventFixture(**item)
            self._events[event.event_id] = event


# Global fixture loader
_loader: Optional[FixtureLoader] = None


def get_fixture_loader() -> FixtureLoader:
    """Get the global fixture loader."""
    global _loader
    if _loader is None:
        _loader = FixtureLoader()
    return _loader


def get_regression_events() -> List[EventFixture]:
    """Convenience function to get all regression events."""
    return get_fixture_loader().get_all_events()
