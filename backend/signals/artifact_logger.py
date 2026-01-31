"""
Artifact Logger.

Logs all run artifacts for traceability and reproducibility.
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from pydantic import BaseModel

from schemas.signal import SignalOutput
from .gate import GateResult


class RunConfig(BaseModel):
    """Configuration for a run."""

    run_id: str
    timestamp: str
    purpose: str
    date_range: Dict[str, str]
    models: Dict[str, str]
    prompt_versions: Dict[str, str]
    thresholds: Dict[str, Any]
    git_commit: Optional[str] = None
    frozen: bool = False


class ArtifactLogger:
    """
    Logs artifacts for a run.

    Creates the following structure:
    runs/<run_id>/
    ├── run_config.json
    ├── signals.csv
    ├── trades.csv
    ├── llm_requests/
    ├── llm_responses/
    ├── summary.json
    └── report.md
    """

    def __init__(self, base_dir: str = "runs"):
        """
        Initialize the logger.

        Args:
            base_dir: Base directory for run artifacts
        """
        self.base_dir = Path(base_dir)

    def create_run(self, config: RunConfig) -> Path:
        """
        Create a new run directory and save config.

        Args:
            config: Run configuration

        Returns:
            Path to run directory
        """
        run_dir = self.base_dir / config.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (run_dir / "llm_requests").mkdir(exist_ok=True)
        (run_dir / "llm_responses").mkdir(exist_ok=True)

        # Save config
        config_path = run_dir / "run_config.json"
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

        return run_dir

    def log_llm_request(
        self,
        run_id: str,
        event_id: str,
        request_data: Dict[str, Any],
    ) -> None:
        """Log an LLM request."""
        run_dir = self.base_dir / run_id / "llm_requests"
        filepath = run_dir / f"{event_id}_request.json"
        with open(filepath, "w") as f:
            json.dump(request_data, f, indent=2)

    def log_llm_response(
        self,
        run_id: str,
        event_id: str,
        response_data: Dict[str, Any],
    ) -> None:
        """Log an LLM response."""
        run_dir = self.base_dir / run_id / "llm_responses"
        filepath = run_dir / f"{event_id}_response.json"
        with open(filepath, "w") as f:
            json.dump(response_data, f, indent=2)

    def log_signals(
        self,
        run_id: str,
        signals: List[SignalOutput],
    ) -> None:
        """
        Log signals to CSV.

        Args:
            run_id: Run identifier
            signals: List of signal outputs
        """
        run_dir = self.base_dir / run_id
        filepath = run_dir / "signals.csv"

        if not signals:
            return

        # Get fieldnames from first signal
        rows = [s.to_csv_row() for s in signals]
        fieldnames = list(rows[0].keys())

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def log_summary(
        self,
        run_id: str,
        summary: Dict[str, Any],
    ) -> None:
        """Log run summary."""
        run_dir = self.base_dir / run_id
        filepath = run_dir / "summary.json"
        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2)

    def log_backtest_request(
        self,
        run_id: str,
        request: Dict[str, Any],
    ) -> None:
        """Log backtest request."""
        run_dir = self.base_dir / run_id
        filepath = run_dir / "backtest_request.json"
        with open(filepath, "w") as f:
            json.dump(request, f, indent=2)

    def log_backtest_result(
        self,
        run_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Log backtest result."""
        run_dir = self.base_dir / run_id
        filepath = run_dir / "backtest_result.json"
        with open(filepath, "w") as f:
            json.dump(result, f, indent=2)

    def generate_report(
        self,
        run_id: str,
        config: RunConfig,
        summary: Dict[str, Any],
        backtest_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate markdown report.

        Args:
            run_id: Run identifier
            config: Run configuration
            summary: Run summary
            backtest_result: Backtest result (if available)

        Returns:
            Report content as markdown string
        """
        lines = []
        lines.append(f"# Run Report: {run_id}")
        lines.append("")
        lines.append(f"**Generated:** {datetime.utcnow().isoformat()}")
        lines.append(f"**Purpose:** {config.purpose}")
        lines.append("")

        lines.append("## Configuration")
        lines.append("")
        lines.append(f"- **Date Range:** {config.date_range.get('start')} to {config.date_range.get('end')}")
        lines.append(f"- **Score Threshold:** {config.thresholds.get('score_threshold')}")
        lines.append(f"- **Evidence Min:** {config.thresholds.get('evidence_min_count')}")
        lines.append(f"- **Batch Score Model:** {config.models.get('batch_score')}")
        lines.append(f"- **Prompt Version:** {config.prompt_versions.get('batch_score')}")
        lines.append("")

        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Events:** {summary.get('total_events', 0)}")
        lines.append(f"- **Signals Generated:** {summary.get('signals_generated', 0)}")
        lines.append(f"- **Trade Signals:** {summary.get('trade_signals', 0)}")
        lines.append(f"- **No Trade Signals:** {summary.get('no_trade_signals', 0)}")
        lines.append(f"- **Total Cost:** ${summary.get('total_cost_usd', 0):.4f}")
        lines.append(f"- **Avg Latency:** {summary.get('avg_latency_ms', 0):.0f}ms")
        lines.append("")

        if backtest_result:
            lines.append("## Backtest Results (from Whaleforce API)")
            lines.append("")
            perf = backtest_result.get("performance", {})
            lines.append(f"- **CAGR:** {perf.get('cagr', 0) * 100:.1f}%")
            lines.append(f"- **Sharpe Ratio:** {perf.get('sharpe_ratio', 0):.2f}")
            lines.append(f"- **Win Rate:** {perf.get('win_rate', 0) * 100:.1f}%")
            lines.append(f"- **Max Drawdown:** {perf.get('max_drawdown', 0) * 100:.1f}%")
            lines.append("")

            stats = backtest_result.get("trade_stats", {})
            lines.append(f"- **Total Trades:** {stats.get('total_trades', 0)}")
            lines.append(f"- **Trades/Year:** {stats.get('trades_per_year', 0):.0f}")
            lines.append("")

        lines.append("## Artifacts")
        lines.append("")
        lines.append(f"- `runs/{run_id}/run_config.json`")
        lines.append(f"- `runs/{run_id}/signals.csv`")
        lines.append(f"- `runs/{run_id}/llm_requests/`")
        lines.append(f"- `runs/{run_id}/llm_responses/`")
        if backtest_result:
            lines.append(f"- `runs/{run_id}/backtest_request.json`")
            lines.append(f"- `runs/{run_id}/backtest_result.json`")
        lines.append("")

        report = "\n".join(lines)

        # Save report
        run_dir = self.base_dir / run_id
        filepath = run_dir / "report.md"
        with open(filepath, "w") as f:
            f.write(report)

        return report


# Global logger instance
_logger: Optional[ArtifactLogger] = None


def get_artifact_logger() -> ArtifactLogger:
    """Get the global artifact logger."""
    global _logger
    if _logger is None:
        _logger = ArtifactLogger()
    return _logger
