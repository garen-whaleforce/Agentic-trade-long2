"""
Evidence Rules.

Validates evidence triangulation requirements.
"""

from typing import List, Optional, Set, Tuple

from pydantic import BaseModel

from schemas.llm_output import Evidence


class EvidenceValidationResult(BaseModel):
    """Result of evidence validation."""

    is_valid: bool
    evidence_count: int
    unique_speakers: int
    unique_sections: int
    is_triangulated: bool
    issues: List[str]


class EvidenceValidator:
    """
    Validates evidence meets triangulation requirements.

    Rules:
    1. Minimum 2 evidence quotes
    2. Must be from different sources (speakers or sections)
    3. Must have actual content (not empty)
    """

    def __init__(
        self,
        min_evidence: int = 2,
        require_triangulation: bool = True,
    ):
        """
        Initialize validator.

        Args:
            min_evidence: Minimum number of evidence quotes
            require_triangulation: Whether triangulation is required
        """
        self.min_evidence = min_evidence
        self.require_triangulation = require_triangulation

    def validate(self, evidence_list: List[Evidence]) -> EvidenceValidationResult:
        """
        Validate a list of evidence.

        Args:
            evidence_list: List of evidence quotes

        Returns:
            EvidenceValidationResult
        """
        issues = []

        # Check minimum count
        if len(evidence_list) < self.min_evidence:
            issues.append(
                f"Insufficient evidence: {len(evidence_list)} < {self.min_evidence}"
            )

        # Check for empty quotes
        empty_quotes = [e for e in evidence_list if not e.quote.strip()]
        if empty_quotes:
            issues.append(f"Found {len(empty_quotes)} empty quotes")

        # Get unique sources
        speakers = set(e.speaker for e in evidence_list)
        sections = set(e.section for e in evidence_list)

        # Check triangulation
        is_triangulated = len(speakers) > 1 or len(sections) > 1

        if self.require_triangulation and not is_triangulated:
            issues.append(
                "Evidence not triangulated: all from same speaker and section"
            )

        return EvidenceValidationResult(
            is_valid=len(issues) == 0,
            evidence_count=len(evidence_list),
            unique_speakers=len(speakers),
            unique_sections=len(sections),
            is_triangulated=is_triangulated,
            issues=issues,
        )

    def calculate_penalty(
        self,
        score: float,
        validation_result: EvidenceValidationResult,
    ) -> float:
        """
        Calculate score penalty based on evidence quality.

        Args:
            score: Original score
            validation_result: Validation result

        Returns:
            Adjusted score
        """
        if validation_result.is_valid:
            return score

        # Apply penalties
        penalty = 1.0

        # Penalty for insufficient evidence
        if validation_result.evidence_count < self.min_evidence:
            if validation_result.evidence_count == 0:
                return 0.0
            elif validation_result.evidence_count == 1:
                penalty *= 0.7

        # Penalty for no triangulation
        if not validation_result.is_triangulated:
            penalty *= 0.9

        return score * penalty


def validate_evidence(evidence_list: List[Evidence]) -> EvidenceValidationResult:
    """Convenience function to validate evidence."""
    validator = EvidenceValidator()
    return validator.validate(evidence_list)
