"""
Company endpoints.

Provides access to company-specific earnings call history.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


# =====================================
# Schemas
# =====================================


class CompanyEvent(BaseModel):
    """Single earnings call event for a company."""

    event_id: str
    fiscal_year: int
    fiscal_quarter: int
    event_date: str
    transcript_available: bool = False


class CompanyEventsResponse(BaseModel):
    """Response for company events endpoint."""

    symbol: str
    company_name: str
    events: List[CompanyEvent]


class CompanyInfo(BaseModel):
    """Basic company information."""

    symbol: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None


# =====================================
# Endpoints
# =====================================


@router.get("/company/{symbol}/events", response_model=CompanyEventsResponse)
async def get_company_events(
    symbol: str,
    start_date: Optional[str] = Query(
        None, description="Start date in YYYY-MM-DD format"
    ),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
) -> CompanyEventsResponse:
    """
    Get earnings call history for a specific company.

    Returns a list of all earnings calls for the company within the date range.
    """
    # TODO: Implement actual API call to EarningsCall API
    # This is a stub response for now

    symbol = symbol.upper()

    # Stub data
    events = []
    for year in range(2017, 2026):
        for quarter in range(1, 5):
            month = (quarter - 1) * 3 + 1
            event_date = f"{year}-{month:02d}-25"
            events.append(
                CompanyEvent(
                    event_id=f"evt_{symbol.lower()}_{year}q{quarter}",
                    fiscal_year=year,
                    fiscal_quarter=quarter,
                    event_date=event_date,
                    transcript_available=True,
                )
            )

    return CompanyEventsResponse(
        symbol=symbol,
        company_name=f"{symbol} Inc.",
        events=events,
    )


@router.get("/company/{symbol}", response_model=CompanyInfo)
async def get_company_info(symbol: str) -> CompanyInfo:
    """
    Get basic information about a company.
    """
    # TODO: Implement actual API call
    # This is a stub response for now

    symbol = symbol.upper()

    companies = {
        "AAPL": CompanyInfo(
            symbol="AAPL",
            company_name="Apple Inc.",
            sector="Technology",
            industry="Consumer Electronics",
        ),
        "MSFT": CompanyInfo(
            symbol="MSFT",
            company_name="Microsoft Corporation",
            sector="Technology",
            industry="Software",
        ),
        "GOOGL": CompanyInfo(
            symbol="GOOGL",
            company_name="Alphabet Inc.",
            sector="Technology",
            industry="Internet Services",
        ),
    }

    if symbol in companies:
        return companies[symbol]

    return CompanyInfo(
        symbol=symbol,
        company_name=f"{symbol} Inc.",
    )
