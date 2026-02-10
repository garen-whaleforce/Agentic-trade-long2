"""
Tests for Golden Set evaluation.

Verifies:
1. GoldenSetEntry schema validation
2. Load/save functionality
3. Evaluation metrics calculation (precision, recall, F1)
4. Score accuracy and flag accuracy
"""

import pytest
import tempfile
import json
from datetime import date
from pathlib import Path

from backend.eval.golden_set import (
    GoldenSet,
    GoldenSetEntry,
    GoldenSetMetrics,
    ExpectedOutput,
    ExpectedKeyFlags,
    create_golden_set_v0,
)


class TestGoldenSetEntry:
    """Unit tests for GoldenSetEntry."""

    def test_create_entry(self):
        """Test creating a golden set entry."""
        entry = GoldenSetEntry(
            entry_id="AAPL_2024-01-01",
            symbol="AAPL",
            event_date=date(2024, 1, 1),
            fiscal_quarter=1,
            fiscal_year=2024,
            company_name="Apple Inc.",
            expected=ExpectedOutput(
                trade_candidate=True,
                score_min=0.6,
                score_max=0.9,
                evidence_min=2,
            ),
            labeled_by="human",
            labeled_at="2026-01-01T00:00:00Z",
            label_confidence=0.95,
        )

        assert entry.entry_id == "AAPL_2024-01-01"
        assert entry.symbol == "AAPL"
        assert entry.expected.trade_candidate is True
        assert entry.expected.score_min == 0.6

    def test_entry_with_flags(self):
        """Test entry with key flags."""
        entry = GoldenSetEntry(
            entry_id="NVDA_2024-05-22",
            symbol="NVDA",
            event_date=date(2024, 5, 22),
            fiscal_quarter=1,
            fiscal_year= 2025,
            company_name="NVIDIA",
            expected=ExpectedOutput(
                trade_candidate=True,
                score_min=0.7,
                score_max=0.95,
                key_flags=ExpectedKeyFlags(
                    guidance_positive=True,
                    revenue_beat=True,
                    guidance_raised=True,
                ),
                evidence_min=3,
            ),
            labeled_by="rule",
            labeled_at="2026-01-01T00:00:00Z",
            label_confidence=0.9,
        )

        assert entry.expected.key_flags.guidance_positive is True
        assert entry.expected.key_flags.margin_concern is None


class TestGoldenSetLoadSave:
    """Tests for load/save functionality."""

    def test_save_and_load(self):
        """Test saving and loading golden set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gs = GoldenSet(path=tmpdir)

            # Add entry
            entry = GoldenSetEntry(
                entry_id="TEST_2024-01-01",
                symbol="TEST",
                event_date=date(2024, 1, 1),
                fiscal_quarter=1,
                fiscal_year=2024,
                company_name="Test Corp",
                expected=ExpectedOutput(
                    trade_candidate=True,
                    score_min=0.5,
                    score_max=0.8,
                    evidence_min=2,
                ),
                labeled_by="test",
                labeled_at="2026-01-01T00:00:00Z",
                label_confidence=1.0,
            )
            gs.add(entry)

            # Save
            gs.save("test.json")

            # Load in new instance
            gs2 = GoldenSet(path=tmpdir)
            count = gs2.load()

            assert count == 1
            assert "TEST_2024-01-01" in gs2.entries

            loaded = gs2.get("TEST_2024-01-01")
            assert loaded.symbol == "TEST"
            assert loaded.expected.trade_candidate is True

    def test_load_empty_directory(self):
        """Test loading from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gs = GoldenSet(path=tmpdir)
            count = gs.load()
            assert count == 0

    def test_get_by_symbol_date(self):
        """Test getting entry by symbol and date."""
        gs = GoldenSet()
        entry = GoldenSetEntry(
            entry_id="AAPL_2024-06-15",
            symbol="AAPL",
            event_date=date(2024, 6, 15),
            fiscal_quarter=2,
            fiscal_year=2024,
            company_name="Apple Inc.",
            expected=ExpectedOutput(
                trade_candidate=False,
                score_min=0.2,
                score_max=0.4,
                evidence_min=1,
            ),
            labeled_by="test",
            labeled_at="2026-01-01T00:00:00Z",
            label_confidence=0.8,
        )
        gs.add(entry)

        found = gs.get_by_symbol_date("AAPL", date(2024, 6, 15))
        assert found is not None
        assert found.symbol == "AAPL"

        not_found = gs.get_by_symbol_date("AAPL", date(2024, 1, 1))
        assert not_found is None


class TestGoldenSetEvaluation:
    """Tests for evaluation metrics."""

    def setup_method(self):
        """Set up test golden set."""
        self.gs = GoldenSet()

        # Add test entries
        entries = [
            # True positive case (expect trade, model says trade)
            ("TP1", True, 0.7, 0.9),
            ("TP2", True, 0.6, 0.85),
            # True negative case (expect no trade, model says no trade)
            ("TN1", False, 0.1, 0.3),
            ("TN2", False, 0.2, 0.4),
            # False positive case (expect no trade, model says trade)
            ("FP1", False, 0.1, 0.3),
            # False negative case (expect trade, model says no trade)
            ("FN1", True, 0.7, 0.9),
        ]

        for entry_id, trade, score_min, score_max in entries:
            entry = GoldenSetEntry(
                entry_id=entry_id,
                symbol=entry_id,
                event_date=date(2024, 1, 1),
                fiscal_quarter=1,
                fiscal_year=2024,
                company_name=f"Test {entry_id}",
                expected=ExpectedOutput(
                    trade_candidate=trade,
                    score_min=score_min,
                    score_max=score_max,
                    evidence_min=1,
                ),
                labeled_by="test",
                labeled_at="2026-01-01T00:00:00Z",
                label_confidence=1.0,
            )
            self.gs.add(entry)

    def test_evaluate_perfect_accuracy(self):
        """Test evaluation with perfect predictions."""
        llm_results = [
            {"event_id": "TP1", "trade_candidate": True, "score": 0.8},
            {"event_id": "TP2", "trade_candidate": True, "score": 0.75},
            {"event_id": "TN1", "trade_candidate": False, "score": 0.2},
            {"event_id": "TN2", "trade_candidate": False, "score": 0.3},
        ]

        # Only use entries that match the llm_results
        gs = GoldenSet()
        for entry_id in ["TP1", "TP2", "TN1", "TN2"]:
            gs.add(self.gs.get(entry_id))

        metrics = gs.evaluate(llm_results)

        assert metrics.true_positives == 2
        assert metrics.true_negatives == 2
        assert metrics.false_positives == 0
        assert metrics.false_negatives == 0
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0

    def test_evaluate_with_errors(self):
        """Test evaluation with prediction errors."""
        llm_results = [
            {"event_id": "TP1", "trade_candidate": True, "score": 0.8},  # TP
            {"event_id": "TN1", "trade_candidate": False, "score": 0.2},  # TN
            {"event_id": "FP1", "trade_candidate": True, "score": 0.6},  # FP (wrong!)
            {"event_id": "FN1", "trade_candidate": False, "score": 0.3},  # FN (wrong!)
        ]

        metrics = self.gs.evaluate(llm_results)

        assert metrics.true_positives == 1
        assert metrics.true_negatives == 1
        assert metrics.false_positives == 1
        assert metrics.false_negatives == 1

        # Precision = 1/(1+1) = 0.5
        assert metrics.precision == 0.5
        # Recall = 1/(1+1) = 0.5
        assert metrics.recall == 0.5

    def test_evaluate_score_accuracy(self):
        """Test score accuracy metrics."""
        llm_results = [
            {"event_id": "TP1", "trade_candidate": True, "score": 0.8},  # Within range
            {"event_id": "TP2", "trade_candidate": True, "score": 0.5},  # Below range
        ]

        gs = GoldenSet()
        gs.add(self.gs.get("TP1"))
        gs.add(self.gs.get("TP2"))

        metrics = gs.evaluate(llm_results)

        assert metrics.score_within_range == 1  # Only TP1 is within range
        assert metrics.total_evaluated == 2

    def test_evaluate_empty_results(self):
        """Test evaluation with empty results."""
        metrics = self.gs.evaluate([])

        assert metrics.precision == 0
        assert metrics.recall == 0
        assert metrics.total_evaluated == 0

    def test_evaluate_flag_accuracy(self):
        """Test flag accuracy calculation."""
        gs = GoldenSet()
        entry = GoldenSetEntry(
            entry_id="FLAG_TEST",
            symbol="FLAG",
            event_date=date(2024, 1, 1),
            fiscal_quarter=1,
            fiscal_year=2024,
            company_name="Flag Test",
            expected=ExpectedOutput(
                trade_candidate=True,
                score_min=0.6,
                score_max=0.9,
                key_flags=ExpectedKeyFlags(
                    guidance_positive=True,
                    revenue_beat=True,
                    margin_concern=False,
                ),
                evidence_min=2,
            ),
            labeled_by="test",
            labeled_at="2026-01-01T00:00:00Z",
            label_confidence=1.0,
        )
        gs.add(entry)

        llm_results = [
            {
                "event_id": "FLAG_TEST",
                "trade_candidate": True,
                "score": 0.75,
                "key_flags": {
                    "guidance_positive": True,  # Correct
                    "revenue_beat": False,  # Wrong
                    "margin_concern": False,  # Correct
                },
            }
        ]

        metrics = gs.evaluate(llm_results)

        # 2 out of 3 flags correct
        assert metrics.flag_accuracy["guidance_positive"] == 1.0
        assert metrics.flag_accuracy["revenue_beat"] == 0.0
        assert metrics.flag_accuracy["margin_concern"] == 1.0


class TestCreateGoldenSetV0:
    """Test golden set v0 creation."""

    def test_create_v0(self):
        """Test creating initial golden set."""
        gs = create_golden_set_v0()

        # Should have some entries
        assert len(gs.entries) >= 2

        # Check NVDA entry exists
        nvda = gs.get("NVDA_2024-05-22")
        assert nvda is not None
        assert nvda.expected.trade_candidate is True

        # Check INTC entry exists (no-trade case)
        intc = gs.get("INTC_2024-04-25")
        assert intc is not None
        assert intc.expected.trade_candidate is False
