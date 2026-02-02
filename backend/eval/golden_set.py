"""
Golden Set for LLM Evaluation.

Provides ground truth labels for evaluating LLM extraction accuracy:
- Precision: How many LLM extractions are correct?
- Recall: How many true positives did the LLM find?
- F1: Harmonic mean of precision and recall

Structure:
- Each entry has a transcript_id + expected outputs
- Expected outputs are human-labeled (or rule-derived)
- Compare LLM output against expected to compute metrics
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import date

from pydantic import BaseModel, Field


class ExpectedKeyFlags(BaseModel):
    """Expected key flags for a transcript."""

    guidance_positive: Optional[bool] = None
    revenue_beat: Optional[bool] = None
    margin_concern: Optional[bool] = None
    guidance_raised: Optional[bool] = None
    buyback_announced: Optional[bool] = None


class ExpectedOutput(BaseModel):
    """Expected LLM output for a transcript."""

    trade_candidate: bool
    score_min: float = Field(ge=0, le=1, description="Minimum acceptable score")
    score_max: float = Field(ge=0, le=1, description="Maximum acceptable score")
    key_flags: ExpectedKeyFlags = Field(default_factory=ExpectedKeyFlags)
    evidence_min: int = Field(ge=0, description="Minimum evidence count")
    no_trade_reason: Optional[str] = None


class GoldenSetEntry(BaseModel):
    """A single golden set entry with ground truth."""

    # Identifiers
    entry_id: str = Field(description="Unique ID: {symbol}_{event_date}")
    symbol: str
    event_date: date
    transcript_id: Optional[str] = None

    # Context
    fiscal_quarter: int = Field(ge=1, le=4)
    fiscal_year: int
    company_name: str

    # Ground truth
    expected: ExpectedOutput

    # Labeling metadata
    labeled_by: str = Field(description="Who labeled this: human/rule/llm-reviewed")
    labeled_at: str = Field(description="ISO timestamp of labeling")
    label_confidence: float = Field(ge=0, le=1, description="Confidence in label")
    notes: Optional[str] = None

    # Actual outcome (for validation)
    actual_price_change_5d: Optional[float] = None
    actual_price_change_30d: Optional[float] = None


class GoldenSetMetrics(BaseModel):
    """Metrics from evaluating against golden set."""

    # Core metrics
    precision: float = Field(description="TP / (TP + FP)")
    recall: float = Field(description="TP / (TP + FN)")
    f1_score: float = Field(description="2 * precision * recall / (precision + recall)")

    # Detailed breakdown
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    # Score accuracy
    score_mae: float = Field(description="Mean absolute error of scores")
    score_within_range: int = Field(description="Count of scores within expected range")

    # Flag accuracy
    flag_accuracy: Dict[str, float] = Field(
        description="Accuracy per flag (guidance_positive, etc.)"
    )

    # Sample sizes
    total_evaluated: int
    total_trade_candidates: int


class GoldenSet:
    """
    Manages golden set entries and evaluation.

    Usage:
        gs = GoldenSet(path="golden_set/")
        gs.load()
        metrics = gs.evaluate(llm_results)
    """

    def __init__(self, path: str = "golden_set"):
        """
        Initialize golden set.

        Args:
            path: Directory containing golden set JSON files
        """
        self.path = Path(path)
        self.entries: Dict[str, GoldenSetEntry] = {}

    def load(self) -> int:
        """
        Load all golden set entries from directory.

        Returns:
            Number of entries loaded
        """
        self.entries = {}

        if not self.path.exists():
            return 0

        for json_file in self.path.glob("*.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)

                # Handle both single entry and list of entries
                if isinstance(data, list):
                    for item in data:
                        entry = GoldenSetEntry(**item)
                        self.entries[entry.entry_id] = entry
                else:
                    entry = GoldenSetEntry(**data)
                    self.entries[entry.entry_id] = entry

            except Exception as e:
                print(f"Warning: Failed to load {json_file}: {e}")

        return len(self.entries)

    def get(self, entry_id: str) -> Optional[GoldenSetEntry]:
        """Get a golden set entry by ID."""
        return self.entries.get(entry_id)

    def get_by_symbol_date(
        self, symbol: str, event_date: date
    ) -> Optional[GoldenSetEntry]:
        """Get entry by symbol and date."""
        entry_id = f"{symbol}_{event_date.isoformat()}"
        return self.get(entry_id)

    def add(self, entry: GoldenSetEntry) -> None:
        """Add an entry to the golden set."""
        self.entries[entry.entry_id] = entry

    def save(self, filename: str = "golden_set_v0.json") -> None:
        """
        Save all entries to a JSON file.

        Args:
            filename: Output filename
        """
        self.path.mkdir(parents=True, exist_ok=True)
        output_path = self.path / filename

        entries_list = [e.model_dump(mode="json") for e in self.entries.values()]

        with open(output_path, "w") as f:
            json.dump(entries_list, f, indent=2, default=str)

    def evaluate(
        self,
        llm_results: List[Dict[str, Any]],
    ) -> GoldenSetMetrics:
        """
        Evaluate LLM results against golden set.

        Args:
            llm_results: List of LLM outputs with event_id, score, trade_candidate, etc.

        Returns:
            GoldenSetMetrics
        """
        # Match results to golden set
        matched = []
        for result in llm_results:
            event_id = result.get("event_id")
            if event_id and event_id in self.entries:
                matched.append((self.entries[event_id], result))

        if not matched:
            return GoldenSetMetrics(
                precision=0,
                recall=0,
                f1_score=0,
                true_positives=0,
                false_positives=0,
                true_negatives=0,
                false_negatives=0,
                score_mae=0,
                score_within_range=0,
                flag_accuracy={},
                total_evaluated=0,
                total_trade_candidates=0,
            )

        # Calculate confusion matrix for trade_candidate
        tp = fp = tn = fn = 0
        score_errors = []
        score_in_range = 0

        flag_correct = {
            "guidance_positive": 0,
            "revenue_beat": 0,
            "margin_concern": 0,
            "guidance_raised": 0,
            "buyback_announced": 0,
        }
        flag_total = {k: 0 for k in flag_correct}

        for expected, actual in matched:
            expected_trade = expected.expected.trade_candidate
            actual_trade = actual.get("trade_candidate", False)

            if expected_trade and actual_trade:
                tp += 1
            elif not expected_trade and actual_trade:
                fp += 1
            elif not expected_trade and not actual_trade:
                tn += 1
            else:
                fn += 1

            # Score accuracy
            actual_score = actual.get("score", 0)
            score_errors.append(
                abs(actual_score - (expected.expected.score_min + expected.expected.score_max) / 2)
            )

            if expected.expected.score_min <= actual_score <= expected.expected.score_max:
                score_in_range += 1

            # Flag accuracy
            actual_flags = actual.get("key_flags", {})
            expected_flags = expected.expected.key_flags

            for flag_name in flag_correct:
                expected_val = getattr(expected_flags, flag_name, None)
                if expected_val is not None:
                    flag_total[flag_name] += 1
                    actual_val = actual_flags.get(flag_name)
                    if actual_val == expected_val:
                        flag_correct[flag_name] += 1

        # Calculate metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        flag_accuracy = {
            k: flag_correct[k] / flag_total[k] if flag_total[k] > 0 else 0
            for k in flag_correct
        }

        return GoldenSetMetrics(
            precision=precision,
            recall=recall,
            f1_score=f1,
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
            score_mae=sum(score_errors) / len(score_errors) if score_errors else 0,
            score_within_range=score_in_range,
            flag_accuracy=flag_accuracy,
            total_evaluated=len(matched),
            total_trade_candidates=tp + fn,
        )


def create_golden_set_v0() -> GoldenSet:
    """
    Create initial golden set v0 with 50 representative entries.

    Categories:
    - 15 clear TRADE (strong positive signals)
    - 15 clear NO_TRADE (weak fundamentals)
    - 10 edge cases (mixed signals)
    - 10 error cases (guidance cut, balance sheet risk)

    Returns:
        GoldenSet with v0 entries
    """
    gs = GoldenSet()

    # These will be populated from actual transcript analysis
    # Placeholder structure for now
    sample_entries = [
        # Clear TRADE examples (guidance raised + beat)
        {
            "entry_id": "NVDA_2024-05-22",
            "symbol": "NVDA",
            "event_date": "2024-05-22",
            "fiscal_quarter": 1,
            "fiscal_year": 2025,
            "company_name": "NVIDIA Corporation",
            "expected": {
                "trade_candidate": True,
                "score_min": 0.7,
                "score_max": 0.95,
                "key_flags": {
                    "guidance_positive": True,
                    "revenue_beat": True,
                    "guidance_raised": True,
                },
                "evidence_min": 3,
            },
            "labeled_by": "rule",
            "labeled_at": "2026-02-02T00:00:00Z",
            "label_confidence": 0.9,
            "notes": "Strong Q1 beat with datacenter growth",
        },
        # Clear NO_TRADE example (margin concern)
        {
            "entry_id": "INTC_2024-04-25",
            "symbol": "INTC",
            "event_date": "2024-04-25",
            "fiscal_quarter": 1,
            "fiscal_year": 2024,
            "company_name": "Intel Corporation",
            "expected": {
                "trade_candidate": False,
                "score_min": 0.1,
                "score_max": 0.4,
                "key_flags": {
                    "guidance_positive": False,
                    "margin_concern": True,
                },
                "evidence_min": 2,
                "no_trade_reason": "margin_concern",
            },
            "labeled_by": "rule",
            "labeled_at": "2026-02-02T00:00:00Z",
            "label_confidence": 0.85,
            "notes": "Gross margin declining, weak guidance",
        },
    ]

    from datetime import datetime

    for entry_data in sample_entries:
        # Convert date string to date object
        entry_data["event_date"] = datetime.fromisoformat(
            entry_data["event_date"]
        ).date()
        entry = GoldenSetEntry(**entry_data)
        gs.add(entry)

    return gs
