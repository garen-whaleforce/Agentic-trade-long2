"""
Company endpoints.

Provides access to company-specific earnings call history.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.earningscall_client import (
    get_earningscall_client,
    EarningsCallAPIError,
    EventNotFoundError,
)

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
    ec_client = get_earningscall_client()
    symbol = symbol.upper()

    try:
        # Parse dates if provided
        parsed_start = date.fromisoformat(start_date) if start_date else None
        parsed_end = date.fromisoformat(end_date) if end_date else None

        response = await ec_client.get_company_events(
            symbol=symbol,
            start_date=parsed_start,
            end_date=parsed_end,
        )

        return CompanyEventsResponse(
            symbol=response.symbol,
            company_name=response.company_name,
            events=[
                CompanyEvent(
                    event_id=event.event_id,
                    fiscal_year=event.fiscal_year,
                    fiscal_quarter=event.fiscal_quarter,
                    event_date=event.event_date,
                    transcript_available=event.transcript_available,
                )
                for event in response.events
            ],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except EventNotFoundError:
        raise HTTPException(status_code=404, detail=f"No events found for symbol: {symbol}")
    except EarningsCallAPIError as e:
        raise HTTPException(status_code=503, detail=f"EarningsCall API error: {str(e)}")


@router.get("/company/{symbol}", response_model=CompanyInfo)
async def get_company_info(symbol: str) -> CompanyInfo:
    """
    Get basic information about a company.

    Derives company info from the most recent earnings event.
    """
    ec_client = get_earningscall_client()
    symbol = symbol.upper()

    try:
        # Get company events to derive company name
        response = await ec_client.get_company_events(symbol=symbol)

        return CompanyInfo(
            symbol=response.symbol,
            company_name=response.company_name,
            # Note: sector/industry not available from EarningsCall API
            sector=None,
            industry=None,
        )

    except EventNotFoundError:
        raise HTTPException(status_code=404, detail=f"Company not found: {symbol}")
    except EarningsCallAPIError as e:
        raise HTTPException(status_code=503, detail=f"EarningsCall API error: {str(e)}")
