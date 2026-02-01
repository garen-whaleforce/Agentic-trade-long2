"""
Earnings call endpoints.

Provides access to earnings call calendar and transcripts.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.earningscall_client import (
    get_earningscall_client,
    EarningsCallAPIError,
    TranscriptNotAvailableError,
    EventNotFoundError,
)

router = APIRouter()


# =====================================
# Schemas
# =====================================


class EarningsEvent(BaseModel):
    """Single earnings call event."""

    event_id: str
    symbol: str
    company_name: str
    fiscal_year: int
    fiscal_quarter: int
    event_date: str
    event_time: Optional[str] = None
    transcript_available: bool = False


class EarningsCalendarResponse(BaseModel):
    """Response for calendar endpoint."""

    date: str
    events: List[EarningsEvent]


class TranscriptSpeaker(BaseModel):
    """Speaker in transcript."""

    name: str
    role: Optional[str] = None
    paragraphs: List[dict]


class TranscriptSection(BaseModel):
    """Section of transcript."""

    speakers: List[TranscriptSpeaker]


class TranscriptResponse(BaseModel):
    """Full transcript response."""

    event_id: str
    symbol: str
    company_name: str
    fiscal_year: int
    fiscal_quarter: int
    event_date: str
    sections: dict
    metadata: dict


# =====================================
# Endpoints
# =====================================


@router.get("/earnings", response_model=EarningsCalendarResponse)
async def get_earnings_by_date(
    query_date: str = Query(..., alias="date", description="Date in YYYY-MM-DD format"),
) -> EarningsCalendarResponse:
    """
    Get earnings calls for a specific date.

    Returns a list of all earnings calls scheduled for the given date.
    """
    ec_client = get_earningscall_client()

    try:
        parsed_date = date.fromisoformat(query_date)
        calendar_response = await ec_client.get_calendar(parsed_date)

        return EarningsCalendarResponse(
            date=query_date,
            events=[
                EarningsEvent(
                    event_id=event.event_id,
                    symbol=event.symbol,
                    company_name=event.company_name,
                    fiscal_year=event.fiscal_year,
                    fiscal_quarter=event.fiscal_quarter,
                    event_date=event.event_date,
                    event_time=event.event_time,
                    transcript_available=event.transcript_available,
                )
                for event in calendar_response.events
            ],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except EarningsCallAPIError as e:
        raise HTTPException(status_code=503, detail=f"EarningsCall API error: {str(e)}")


@router.get("/transcript/{event_id}", response_model=TranscriptResponse)
async def get_transcript(event_id: str) -> TranscriptResponse:
    """
    Get transcript for a specific earnings call event.

    Returns the full transcript with prepared remarks and Q&A sections.
    """
    ec_client = get_earningscall_client()

    try:
        transcript = await ec_client.get_transcript(event_id)

        return TranscriptResponse(
            event_id=transcript.event_id,
            symbol=transcript.symbol,
            company_name=transcript.company_name,
            fiscal_year=transcript.fiscal_year,
            fiscal_quarter=transcript.fiscal_quarter,
            event_date=transcript.event_date,
            sections=transcript.sections,
            metadata=transcript.metadata,
        )

    except EventNotFoundError:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
    except TranscriptNotAvailableError:
        raise HTTPException(status_code=422, detail=f"Transcript not available for: {event_id}")
    except EarningsCallAPIError as e:
        raise HTTPException(status_code=503, detail=f"EarningsCall API error: {str(e)}")
