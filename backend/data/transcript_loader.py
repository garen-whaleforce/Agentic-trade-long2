"""
Transcript Loader.

Loads and validates transcripts from the EarningsCall API.
"""

from datetime import date
from typing import Optional, List, Dict, Any

from pydantic import BaseModel

from services.earningscall_client import (
    get_earningscall_client,
    TranscriptResponse,
    TranscriptNotAvailableError,
    EventNotFoundError,
)


class TranscriptMetadata(BaseModel):
    """Metadata about a loaded transcript."""

    event_id: str
    symbol: str
    company_name: str
    fiscal_year: int
    fiscal_quarter: int
    event_date: str
    word_count: int
    speaker_count: int
    has_prepared_remarks: bool
    has_qa_session: bool


class TranscriptLoader:
    """
    Loads transcripts with validation.

    Ensures transcripts meet minimum requirements before processing.
    """

    def __init__(self, min_word_count: int = 1000, require_qa: bool = False):
        """
        Initialize the loader.

        Args:
            min_word_count: Minimum word count for valid transcript
            require_qa: Whether Q&A section is required
        """
        self.min_word_count = min_word_count
        self.require_qa = require_qa
        self._client = get_earningscall_client()

    async def load(self, event_id: str) -> TranscriptResponse:
        """
        Load a transcript.

        Args:
            event_id: Event identifier

        Returns:
            TranscriptResponse

        Raises:
            TranscriptNotAvailableError: If transcript doesn't exist
            EventNotFoundError: If event doesn't exist
            ValueError: If transcript doesn't meet requirements
        """
        transcript = await self._client.get_transcript(event_id)

        # Validate
        self._validate(transcript)

        return transcript

    def _validate(self, transcript: TranscriptResponse) -> None:
        """Validate transcript meets requirements."""
        # Check word count
        word_count = transcript.metadata.get("word_count", 0)
        if word_count < self.min_word_count:
            raise ValueError(
                f"Transcript too short: {word_count} words < {self.min_word_count}"
            )

        # Check for Q&A if required
        if self.require_qa:
            qa = transcript.sections.get("qa_session", {})
            if not qa.get("exchanges"):
                raise ValueError("Transcript missing Q&A session")

    def get_metadata(self, transcript: TranscriptResponse) -> TranscriptMetadata:
        """Extract metadata from transcript."""
        sections = transcript.sections

        # Count speakers
        speaker_count = 0
        if "prepared_remarks" in sections:
            speaker_count += len(sections["prepared_remarks"].get("speakers", []))

        # Check sections
        has_prepared = bool(sections.get("prepared_remarks", {}).get("speakers"))
        has_qa = bool(sections.get("qa_session", {}).get("exchanges"))

        return TranscriptMetadata(
            event_id=transcript.event_id,
            symbol=transcript.symbol,
            company_name=transcript.company_name,
            fiscal_year=transcript.fiscal_year,
            fiscal_quarter=transcript.fiscal_quarter,
            event_date=transcript.event_date,
            word_count=transcript.metadata.get("word_count", 0),
            speaker_count=speaker_count,
            has_prepared_remarks=has_prepared,
            has_qa_session=has_qa,
        )

    async def load_with_metadata(
        self, event_id: str
    ) -> tuple[TranscriptResponse, TranscriptMetadata]:
        """Load transcript and extract metadata."""
        transcript = await self.load(event_id)
        metadata = self.get_metadata(transcript)
        return transcript, metadata
