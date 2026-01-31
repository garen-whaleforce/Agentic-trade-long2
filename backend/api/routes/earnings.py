"""
Earnings call endpoints.

Provides access to earnings call calendar and transcripts.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
) -> EarningsCalendarResponse:
    """
    Get earnings calls for a specific date.

    Returns a list of all earnings calls scheduled for the given date.
    """
    # TODO: Implement actual API call to EarningsCall API
    # This is a stub response for now

    return EarningsCalendarResponse(
        date=date,
        events=[
            EarningsEvent(
                event_id=f"evt_aapl_{date.replace('-', '')}",
                symbol="AAPL",
                company_name="Apple Inc.",
                fiscal_year=2024,
                fiscal_quarter=1,
                event_date=date,
                event_time="16:30:00",
                transcript_available=True,
            ),
            EarningsEvent(
                event_id=f"evt_msft_{date.replace('-', '')}",
                symbol="MSFT",
                company_name="Microsoft Corporation",
                fiscal_year=2024,
                fiscal_quarter=2,
                event_date=date,
                event_time="17:00:00",
                transcript_available=True,
            ),
        ],
    )


@router.get("/transcript/{event_id}", response_model=TranscriptResponse)
async def get_transcript(event_id: str) -> TranscriptResponse:
    """
    Get transcript for a specific earnings call event.

    Returns the full transcript with prepared remarks and Q&A sections.
    """
    # TODO: Implement actual API call to EarningsCall API
    # This is a stub response for now

    return TranscriptResponse(
        event_id=event_id,
        symbol="AAPL",
        company_name="Apple Inc.",
        fiscal_year=2024,
        fiscal_quarter=1,
        event_date="2024-01-25",
        sections={
            "prepared_remarks": {
                "speakers": [
                    {
                        "name": "Tim Cook",
                        "role": "CEO",
                        "paragraphs": [
                            {
                                "index": 0,
                                "text": "Good afternoon everyone, and thank you for joining us today.",
                            },
                            {
                                "index": 1,
                                "text": "We're pleased to report strong results for the quarter.",
                            },
                        ],
                    },
                    {
                        "name": "Luca Maestri",
                        "role": "CFO",
                        "paragraphs": [
                            {
                                "index": 0,
                                "text": "Thank you, Tim. Revenue for the quarter was $119.6 billion.",
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
                        "question": "Can you provide more color on the services growth?",
                        "answers": [
                            {
                                "speaker": "Tim Cook",
                                "text": "Services continues to be a key growth driver...",
                            }
                        ],
                    }
                ]
            },
        },
        metadata={
            "word_count": 12500,
            "duration_minutes": 60,
        },
    )
