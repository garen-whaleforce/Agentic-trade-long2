"""
Time axis schemas.

Defines the SSOT for T day, entry date (T+1 close), and exit date (T+30 close).
All time calculations must go through these schemas.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class TradingDates(BaseModel):
    """
    Trading dates for a single event.

    SSOT for:
    - T day: earnings call publish date
    - Entry: T+1 trading day close
    - Exit: T+30 trading day close
    """

    t_day: date = Field(..., description="Event day (earnings call publish date)")
    entry_date: date = Field(..., description="T+1 trading day close")
    exit_date: date = Field(..., description="T+30 trading day close")

    @model_validator(mode="after")
    def validate_dates(self) -> "TradingDates":
        """Ensure dates are in correct order."""
        if self.entry_date <= self.t_day:
            raise ValueError(
                f"entry_date ({self.entry_date}) must be after t_day ({self.t_day})"
            )
        if self.exit_date <= self.entry_date:
            raise ValueError(
                f"exit_date ({self.exit_date}) must be after entry_date ({self.entry_date})"
            )
        return self


class TimeAxis(BaseModel):
    """
    Complete time axis for an earnings event analysis.

    Includes the event metadata and calculated trading dates.
    """

    event_id: str
    symbol: str
    fiscal_year: int
    fiscal_quarter: int

    # Core dates
    dates: TradingDates

    # Metadata
    trading_days_between: int = Field(
        ..., description="Number of trading days between entry and exit"
    )

    @property
    def t_day(self) -> date:
        return self.dates.t_day

    @property
    def entry_date(self) -> date:
        return self.dates.entry_date

    @property
    def exit_date(self) -> date:
        return self.dates.exit_date

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "symbol": self.symbol,
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": self.fiscal_quarter,
            "t_day": self.dates.t_day.isoformat(),
            "entry_date": self.dates.entry_date.isoformat(),
            "exit_date": self.dates.exit_date.isoformat(),
            "trading_days_between": self.trading_days_between,
        }
