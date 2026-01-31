"""
Earnings Call API Client.

Unified interface for accessing earnings call calendar, company events, and transcripts.
"""

from datetime import date
from typing import List, Optional, Dict, Any
import hashlib
import json
import os

import httpx
from pydantic import BaseModel

from core.config import settings


# =====================================
# Response Models
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


class CalendarResponse(BaseModel):
    """Response for calendar endpoint."""

    date: str
    events: List[EarningsEvent]


class CompanyEvent(BaseModel):
    """Event for a specific company."""

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


class TranscriptParagraph(BaseModel):
    """Single paragraph in transcript."""

    index: int
    text: str


class TranscriptSpeaker(BaseModel):
    """Speaker in transcript."""

    name: str
    role: Optional[str] = None
    paragraphs: List[TranscriptParagraph]


class QAExchange(BaseModel):
    """Q&A exchange in transcript."""

    analyst: str
    firm: Optional[str] = None
    question: str
    answers: List[Dict[str, str]]


class TranscriptResponse(BaseModel):
    """Full transcript response."""

    event_id: str
    symbol: str
    company_name: str
    fiscal_year: int
    fiscal_quarter: int
    event_date: str
    sections: Dict[str, Any]
    metadata: Dict[str, Any]


# =====================================
# Exceptions
# =====================================


class EarningsCallAPIError(Exception):
    """Base exception for Earnings Call API errors."""

    pass


class TranscriptNotAvailableError(EarningsCallAPIError):
    """Transcript is not available."""

    pass


class EventNotFoundError(EarningsCallAPIError):
    """Event not found."""

    pass


class APIConnectionError(EarningsCallAPIError):
    """API connection error."""

    pass


# =====================================
# Client
# =====================================


class EarningsCallClient:
    """
    Client for Earnings Call API.

    Provides access to:
    - Calendar (earnings calls by date)
    - Company events (earnings call history for a company)
    - Transcripts (full transcript content)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ):
        """
        Initialize the client.

        Args:
            api_key: API key for authentication
            base_url: Base URL for the API
            cache_dir: Directory for caching responses
        """
        self.api_key = api_key or settings.earningscall_api_key
        self.base_url = base_url or settings.earningscall_api_url
        self.cache_dir = cache_dir or os.path.join(settings.cache_dir, "earningscall")

        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    def _get_cache_path(self, cache_type: str, key: str) -> str:
        """Get the cache file path."""
        subdir = os.path.join(self.cache_dir, cache_type)
        os.makedirs(subdir, exist_ok=True)
        return os.path.join(subdir, f"{key}.json")

    def _read_cache(self, cache_type: str, key: str) -> Optional[Dict]:
        """Read from cache if available."""
        cache_path = self._get_cache_path(cache_type, key)
        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                return json.load(f)
        return None

    def _write_cache(self, cache_type: str, key: str, data: Dict) -> None:
        """Write to cache."""
        cache_path = self._get_cache_path(cache_type, key)
        with open(cache_path, "w") as f:
            json.dump(data, f)

    async def get_calendar(self, query_date: date) -> CalendarResponse:
        """
        Get earnings calls for a specific date.

        Args:
            query_date: Date to query

        Returns:
            CalendarResponse with list of events
        """
        date_str = query_date.isoformat()

        # Check cache
        cached = self._read_cache("calendar", date_str)
        if cached:
            return CalendarResponse(**cached)

        try:
            response = await self._client.get(
                "/calendar", params={"date": date_str}
            )
            response.raise_for_status()
            data = response.json()

            # Cache the response
            self._write_cache("calendar", date_str, data)

            return CalendarResponse(**data)

        except httpx.HTTPStatusError as e:
            raise APIConnectionError(f"API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIConnectionError(f"Connection error: {str(e)}")

    async def get_company_events(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> CompanyEventsResponse:
        """
        Get earnings call history for a company.

        Args:
            symbol: Stock symbol
            start_date: Start date filter
            end_date: End date filter

        Returns:
            CompanyEventsResponse with list of events
        """
        symbol = symbol.upper()
        cache_key = f"{symbol}_{start_date}_{end_date}"

        # Check cache
        cached = self._read_cache("company", cache_key)
        if cached:
            return CompanyEventsResponse(**cached)

        try:
            params = {"symbol": symbol}
            if start_date:
                params["start_date"] = start_date.isoformat()
            if end_date:
                params["end_date"] = end_date.isoformat()

            response = await self._client.get("/company/events", params=params)
            response.raise_for_status()
            data = response.json()

            # Cache the response
            self._write_cache("company", cache_key, data)

            return CompanyEventsResponse(**data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise EventNotFoundError(f"No events found for {symbol}")
            raise APIConnectionError(f"API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIConnectionError(f"Connection error: {str(e)}")

    async def get_transcript(self, event_id: str) -> TranscriptResponse:
        """
        Get transcript for an earnings call.

        Transcripts are permanently cached (content doesn't change).

        Args:
            event_id: Event identifier

        Returns:
            TranscriptResponse with full transcript
        """
        # Check cache (transcripts are permanent)
        cached = self._read_cache("transcript", event_id)
        if cached:
            return TranscriptResponse(**cached)

        try:
            response = await self._client.get(f"/transcript/{event_id}")
            response.raise_for_status()
            data = response.json()

            # Cache the response permanently
            self._write_cache("transcript", event_id, data)

            return TranscriptResponse(**data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise EventNotFoundError(f"Event not found: {event_id}")
            if e.response.status_code == 422:
                raise TranscriptNotAvailableError(
                    f"Transcript not available for {event_id}"
                )
            raise APIConnectionError(f"API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIConnectionError(f"Connection error: {str(e)}")


# =====================================
# Singleton instance
# =====================================

_client: Optional[EarningsCallClient] = None


def get_earningscall_client() -> EarningsCallClient:
    """Get the singleton EarningsCall client."""
    global _client
    if _client is None:
        _client = EarningsCallClient()
    return _client
