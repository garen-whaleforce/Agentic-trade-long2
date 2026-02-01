"""
Transcript Pack Builder.

Builds a condensed "transcript pack" for LLM analysis with:
- Controlled token budget
- Speaker and section tracking
- Citation references for evidence triangulation
"""

from datetime import date
from typing import List, Optional, Dict, Any
import hashlib
import json

from pydantic import BaseModel

from services.earningscall_client import TranscriptResponse


class TranscriptSnippet(BaseModel):
    """A snippet from the transcript with citation info."""

    text: str
    speaker: str
    role: Optional[str] = None
    section: str  # "prepared" or "qa"
    paragraph_index: int
    char_start: int
    char_end: int

    def to_citation(self) -> str:
        """Generate citation string."""
        role_str = f" ({self.role})" if self.role else ""
        return f"{self.speaker}{role_str}, {self.section}, ¶{self.paragraph_index}"


class TranscriptPack(BaseModel):
    """
    Condensed transcript pack for LLM analysis.

    Contains:
    - Snippets organized by section
    - Metadata for citation
    - Token estimate
    """

    event_id: str
    symbol: str
    company_name: str
    fiscal_year: int
    fiscal_quarter: int
    event_date: str

    # Content
    prepared_remarks: List[TranscriptSnippet]
    qa_session: List[TranscriptSnippet]

    # Metadata
    total_snippets: int
    estimated_tokens: int
    pack_version: str
    pack_hash: str

    def to_llm_context(self) -> str:
        """
        Convert to formatted string for LLM context.

        Returns:
            Formatted transcript string
        """
        lines = []
        lines.append(f"=== EARNINGS CALL TRANSCRIPT ===")
        lines.append(f"Company: {self.symbol} - {self.company_name}")
        lines.append(f"Period: Q{self.fiscal_quarter} {self.fiscal_year}")
        lines.append(f"Date: {self.event_date}")
        lines.append("")

        if self.prepared_remarks:
            lines.append("--- PREPARED REMARKS ---")
            for snippet in self.prepared_remarks:
                lines.append(f"[{snippet.to_citation()}]")
                lines.append(snippet.text)
                lines.append("")

        if self.qa_session:
            lines.append("--- Q&A SESSION ---")
            for snippet in self.qa_session:
                lines.append(f"[{snippet.to_citation()}]")
                lines.append(snippet.text)
                lines.append("")

        lines.append("=== END TRANSCRIPT ===")

        return "\n".join(lines)


class TranscriptPackBuilder:
    """
    Builds transcript packs with token budget control.

    Strategy:
    1. Include all executive speakers (CEO, CFO, COO)
    2. Prioritize guidance-related content
    3. Include Q&A exchanges with analysts
    4. Truncate to fit token budget
    """

    # Token estimation: ~4 chars per token
    CHARS_PER_TOKEN = 4

    # Priority keywords for content selection
    PRIORITY_KEYWORDS = [
        "guidance",
        "outlook",
        "expect",
        "forecast",
        "growth",
        "revenue",
        "earnings",
        "margin",
        "profit",
        "quarter",
        "year",
        "target",
        "achieve",
        "momentum",
        "strong",
        "weak",
        "challenge",
        "opportunity",
    ]

    # Executive roles to prioritize
    EXECUTIVE_ROLES = ["CEO", "CFO", "COO", "President", "Chairman"]

    def __init__(
        self,
        max_tokens: int = 3000,
        pack_version: str = "v1.0.0",
    ):
        """
        Initialize the builder.

        Args:
            max_tokens: Maximum tokens in the pack
            pack_version: Version identifier for the pack format
        """
        self.max_tokens = max_tokens
        self.pack_version = pack_version
        self.max_chars = max_tokens * self.CHARS_PER_TOKEN

    def build(self, transcript: TranscriptResponse) -> TranscriptPack:
        """
        Build a transcript pack from a full transcript.

        Args:
            transcript: Full transcript response

        Returns:
            TranscriptPack with condensed content
        """
        prepared_snippets = self._extract_prepared_remarks(transcript)
        qa_snippets = self._extract_qa_session(transcript)

        # Calculate current size
        all_snippets = prepared_snippets + qa_snippets
        total_chars = sum(len(s.text) for s in all_snippets)

        # Truncate if needed
        if total_chars > self.max_chars:
            all_snippets = self._truncate_to_budget(all_snippets)

        # Split back into sections
        prepared = [s for s in all_snippets if s.section == "prepared"]
        qa = [s for s in all_snippets if s.section == "qa"]

        # Calculate hash
        pack_content = json.dumps(
            {
                "event_id": transcript.event_id,
                "pack_version": self.pack_version,
                "snippets": [s.model_dump() for s in all_snippets],
            },
            sort_keys=True,
        )
        pack_hash = hashlib.sha256(pack_content.encode()).hexdigest()[:16]

        total_chars = sum(len(s.text) for s in all_snippets)
        estimated_tokens = total_chars // self.CHARS_PER_TOKEN

        return TranscriptPack(
            event_id=transcript.event_id,
            symbol=transcript.symbol,
            company_name=transcript.company_name,
            fiscal_year=transcript.fiscal_year,
            fiscal_quarter=transcript.fiscal_quarter,
            event_date=transcript.event_date,
            prepared_remarks=prepared,
            qa_session=qa,
            total_snippets=len(all_snippets),
            estimated_tokens=estimated_tokens,
            pack_version=self.pack_version,
            pack_hash=pack_hash,
        )

    def _extract_prepared_remarks(
        self, transcript: TranscriptResponse
    ) -> List[TranscriptSnippet]:
        """Extract snippets from prepared remarks section."""
        snippets = []

        prepared = transcript.sections.get("prepared_remarks", {})
        speakers = prepared.get("speakers", [])

        char_offset = 0

        for speaker_data in speakers:
            speaker_name = speaker_data.get("name", "Unknown")
            speaker_role = speaker_data.get("role")
            paragraphs = speaker_data.get("paragraphs", [])

            # Prioritize executives
            is_executive = any(
                role in (speaker_role or "").upper()
                for role in self.EXECUTIVE_ROLES
            )

            for para in paragraphs:
                text = para.get("text", "")
                para_index = para.get("index", 0)

                # Calculate priority score
                priority = self._calculate_priority(text, is_executive)

                if priority > 0 or is_executive:
                    snippets.append(
                        TranscriptSnippet(
                            text=text,
                            speaker=speaker_name,
                            role=speaker_role,
                            section="prepared",
                            paragraph_index=para_index,
                            char_start=char_offset,
                            char_end=char_offset + len(text),
                        )
                    )

                char_offset += len(text) + 1

        return snippets

    def _extract_qa_session(
        self, transcript: TranscriptResponse
    ) -> List[TranscriptSnippet]:
        """Extract snippets from Q&A session."""
        snippets = []

        qa = transcript.sections.get("qa_session", {})
        exchanges = qa.get("exchanges", [])

        char_offset = 0

        for idx, exchange in enumerate(exchanges):
            analyst = exchange.get("analyst", "Analyst")
            question = exchange.get("question", "")
            answers = exchange.get("answers", [])

            # Add question
            if question:
                snippets.append(
                    TranscriptSnippet(
                        text=f"Q: {question}",
                        speaker=analyst,
                        role="Analyst",
                        section="qa",
                        paragraph_index=idx * 2,
                        char_start=char_offset,
                        char_end=char_offset + len(question),
                    )
                )
                char_offset += len(question) + 1

            # Add answers
            for answer in answers:
                answer_text = answer.get("text", "")
                answer_speaker = answer.get("speaker", "Executive")

                if answer_text:
                    snippets.append(
                        TranscriptSnippet(
                            text=f"A: {answer_text}",
                            speaker=answer_speaker,
                            role="Executive",
                            section="qa",
                            paragraph_index=idx * 2 + 1,
                            char_start=char_offset,
                            char_end=char_offset + len(answer_text),
                        )
                    )
                    char_offset += len(answer_text) + 1

        return snippets

    def _calculate_priority(self, text: str, is_executive: bool) -> int:
        """Calculate priority score for a snippet."""
        score = 0
        text_lower = text.lower()

        for keyword in self.PRIORITY_KEYWORDS:
            if keyword in text_lower:
                score += 1

        if is_executive:
            score += 2

        return score

    def _truncate_to_budget(
        self, snippets: List[TranscriptSnippet]
    ) -> List[TranscriptSnippet]:
        """Truncate snippets to fit within token budget."""
        # Sort by priority (executives first, then by keyword count)
        def priority_key(s: TranscriptSnippet) -> tuple:
            is_exec = s.role in self.EXECUTIVE_ROLES if s.role else False
            keyword_count = self._calculate_priority(s.text, is_exec)
            return (-int(is_exec), -keyword_count, s.paragraph_index)

        sorted_snippets = sorted(snippets, key=priority_key)

        result = []
        total_chars = 0

        for snippet in sorted_snippets:
            if total_chars + len(snippet.text) <= self.max_chars:
                result.append(snippet)
                total_chars += len(snippet.text)

        # Re-sort by original order (section, then paragraph index)
        result.sort(
            key=lambda s: (0 if s.section == "prepared" else 1, s.paragraph_index)
        )

        return result
