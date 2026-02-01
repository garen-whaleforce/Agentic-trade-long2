"""
Tests for PR4: Artifacts Schema.

Tests the standardized artifact format for backtest/paper trading.
"""

import pytest
import json
import tempfile
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from schemas.artifacts import (
    RunType,
    RunStatus,
    PromptArtifact,
    ModelArtifact,
    ThresholdArtifact,
    RunManifest,
    SignalArtifact,
    PositionArtifact,
    PerformanceArtifact,
    RunSummary,
    RunArtifacts,
    create_run_manifest,
)


class TestRunManifest:
    """Test RunManifest creation and hashing."""

    def test_create_manifest_basic(self):
        """Should create a manifest with basic fields."""
        manifest = create_run_manifest(
            run_id="test_run_001",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2017-01-01",
            end_date="2021-12-31",
        )

        assert manifest.run_id == "test_run_001"
        assert manifest.run_type == RunType.BACKTEST_TUNE
        assert manifest.start_date == "2017-01-01"
        assert manifest.end_date == "2021-12-31"
        assert manifest.manifest_hash != ""

    def test_manifest_hash_deterministic(self):
        """Same inputs should produce same hash."""
        manifest1 = create_run_manifest(
            run_id="test",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
            model_id="gpt-4o-mini",
            prompt_hash="abc123",
        )

        manifest2 = create_run_manifest(
            run_id="test",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
            model_id="gpt-4o-mini",
            prompt_hash="abc123",
        )

        assert manifest1.manifest_hash == manifest2.manifest_hash

    def test_manifest_hash_changes_with_config(self):
        """Different configs should produce different hashes."""
        manifest1 = create_run_manifest(
            run_id="test",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
            score_threshold=0.70,
        )

        manifest2 = create_run_manifest(
            run_id="test",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
            score_threshold=0.75,  # Different threshold
        )

        assert manifest1.manifest_hash != manifest2.manifest_hash

    def test_manifest_includes_prompt_hash(self):
        """Manifest should include prompt_hash (PR2 integration)."""
        manifest = create_run_manifest(
            run_id="test",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
            prompt_hash="sha256_of_prompt",
        )

        assert manifest.prompt_config.prompt_hash == "sha256_of_prompt"


class TestSignalArtifact:
    """Test SignalArtifact creation."""

    def test_create_signal(self):
        """Should create a signal artifact."""
        signal = SignalArtifact(
            event_id="evt_aapl_2024q1",
            symbol="AAPL",
            event_date="2024-01-25",
            signal_date="2024-01-26",
            score=0.82,
            trade_candidate=True,
            evidence_count=3,
            key_flags={"guidance_positive": True, "revenue_beat": True},
            entry_date="2024-01-26",
            exit_date="2024-02-25",
            passed_gate=True,
        )

        assert signal.symbol == "AAPL"
        assert signal.score == 0.82
        assert signal.trade_candidate is True
        assert signal.passed_gate is True

    def test_signal_with_no_trade(self):
        """Should handle no-trade signals."""
        signal = SignalArtifact(
            event_id="evt_msft_2024q1",
            symbol="MSFT",
            event_date="2024-01-25",
            signal_date="2024-01-26",
            score=0.45,
            trade_candidate=False,
            evidence_count=1,
            key_flags={},
            no_trade_reason="Score below threshold",
            passed_gate=False,
            gate_reason="score_threshold_not_met",
        )

        assert signal.trade_candidate is False
        assert signal.no_trade_reason is not None
        assert signal.passed_gate is False


class TestPositionArtifact:
    """Test PositionArtifact creation."""

    def test_create_position(self):
        """Should create a position artifact."""
        position = PositionArtifact(
            symbol="AAPL",
            entry_date="2024-01-26",
            exit_date="2024-02-25",
            signal_id="evt_aapl_2024q1",
            score=0.82,
            weight=0.05,
        )

        assert position.symbol == "AAPL"
        assert position.direction == "long"
        assert position.weight == 0.05

    def test_position_with_prices(self):
        """Should store price data from backtest."""
        position = PositionArtifact(
            symbol="AAPL",
            entry_date="2024-01-26",
            exit_date="2024-02-25",
            signal_id="evt_aapl_2024q1",
            score=0.82,
            entry_price=185.50,
            exit_price=195.25,
            return_pct=0.0525,
        )

        assert position.entry_price == 185.50
        assert position.exit_price == 195.25
        assert position.return_pct == 0.0525


class TestPerformanceArtifact:
    """Test PerformanceArtifact creation."""

    def test_create_performance(self):
        """Should create performance artifact."""
        perf = PerformanceArtifact(
            cagr=0.35,
            sharpe_ratio=2.1,
            max_drawdown=0.15,
            win_rate=0.72,
            total_trades=150,
            trades_per_year=30,
            source="whaleforce_api",
            backtest_id="bt_12345",
        )

        assert perf.cagr == 0.35
        assert perf.sharpe_ratio == 2.1
        assert perf.source == "whaleforce_api"

    def test_performance_requires_api_source(self):
        """Performance should always indicate API source."""
        perf = PerformanceArtifact()
        assert perf.source == "whaleforce_api"


class TestRunArtifacts:
    """Test RunArtifacts container."""

    def test_create_run_artifacts(self):
        """Should create complete run artifacts."""
        manifest = create_run_manifest(
            run_id="test_run",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
        )

        artifacts = RunArtifacts(manifest=manifest)

        assert artifacts.manifest.run_id == "test_run"
        assert len(artifacts.signals) == 0
        assert len(artifacts.positions) == 0

    def test_add_signals_and_positions(self):
        """Should add signals and positions."""
        manifest = create_run_manifest(
            run_id="test_run",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
        )

        signal = SignalArtifact(
            event_id="evt1",
            symbol="AAPL",
            event_date="2020-01-15",
            signal_date="2020-01-16",
            score=0.8,
            trade_candidate=True,
            evidence_count=3,
            key_flags={},
            passed_gate=True,
        )

        position = PositionArtifact(
            symbol="AAPL",
            entry_date="2020-01-16",
            exit_date="2020-02-15",
            signal_id="evt1",
            score=0.8,
        )

        artifacts = RunArtifacts(
            manifest=manifest,
            signals=[signal],
            positions=[position],
        )

        assert len(artifacts.signals) == 1
        assert len(artifacts.positions) == 1
        assert artifacts.signals[0].symbol == "AAPL"

    def test_add_checkpoint(self):
        """Should add validation checkpoints."""
        manifest = create_run_manifest(
            run_id="test_run",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
        )

        artifacts = RunArtifacts(manifest=manifest)
        artifacts.add_checkpoint("gate_validation", {"passed": 100, "failed": 50})

        assert "gate_validation" in artifacts.checkpoints
        assert artifacts.checkpoints["gate_validation"]["data"]["passed"] == 100

    def test_save_and_load(self, tmp_path):
        """Should save and load artifacts."""
        manifest = create_run_manifest(
            run_id="test_run",
            run_type=RunType.BACKTEST_TUNE,
            start_date="2020-01-01",
            end_date="2020-12-31",
        )

        signal = SignalArtifact(
            event_id="evt1",
            symbol="AAPL",
            event_date="2020-01-15",
            signal_date="2020-01-16",
            score=0.8,
            trade_candidate=True,
            evidence_count=3,
            key_flags={"guidance_positive": True},
            passed_gate=True,
        )

        artifacts = RunArtifacts(
            manifest=manifest,
            signals=[signal],
        )

        # Save
        path = tmp_path / "artifacts.json"
        artifacts.save(str(path))

        # Load
        loaded = RunArtifacts.load(str(path))

        assert loaded.manifest.run_id == "test_run"
        assert len(loaded.signals) == 1
        assert loaded.signals[0].symbol == "AAPL"


class TestRunTypes:
    """Test different run types."""

    def test_all_run_types(self):
        """Should support all run types."""
        run_types = [
            RunType.BACKTEST_TUNE,
            RunType.BACKTEST_VALIDATE,
            RunType.BACKTEST_FINAL,
            RunType.PAPER_TRADING,
            RunType.SMOKE_TEST,
        ]

        for run_type in run_types:
            manifest = create_run_manifest(
                run_id=f"test_{run_type.value}",
                run_type=run_type,
                start_date="2020-01-01",
                end_date="2020-12-31",
            )
            assert manifest.run_type == run_type


class TestRunSummary:
    """Test RunSummary creation."""

    def test_create_summary(self):
        """Should create run summary."""
        summary = RunSummary(
            run_id="test_run",
            run_type=RunType.BACKTEST_TUNE,
            status=RunStatus.COMPLETED,
            total_events=100,
            processed_events=100,
            trade_signals=25,
            no_trade_signals=75,
            total_cost_usd=2.50,
        )

        assert summary.total_events == 100
        assert summary.trade_signals == 25
        assert summary.status == RunStatus.COMPLETED

    def test_summary_with_performance(self):
        """Should include performance metrics."""
        perf = PerformanceArtifact(
            cagr=0.30,
            sharpe_ratio=1.8,
            total_trades=50,
        )

        summary = RunSummary(
            run_id="test_run",
            run_type=RunType.BACKTEST_TUNE,
            status=RunStatus.COMPLETED,
            performance=perf,
        )

        assert summary.performance.cagr == 0.30
