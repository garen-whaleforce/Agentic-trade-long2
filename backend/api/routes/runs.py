"""
Runs endpoints.

Provides access to run artifacts and history.
"""

import csv
from datetime import date
from typing import List, Optional, Dict, Any
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Base directory for run artifacts
RUNS_DIR = Path("runs")


class RunSummary(BaseModel):
    """Summary of a single run."""

    run_id: str
    timestamp: str
    purpose: str
    date_range: Dict[str, str]
    total_signals: int
    trade_signals: int
    models: Dict[str, str]
    has_backtest: bool


class RunDetail(BaseModel):
    """Detailed run information."""

    run_id: str
    config: Dict[str, Any]
    summary: Optional[Dict[str, Any]] = None
    backtest_result: Optional[Dict[str, Any]] = None


class RunsList(BaseModel):
    """List of runs."""

    runs: List[RunSummary]
    total: int


def _load_json_file(filepath: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file safely."""
    if filepath.exists():
        with open(filepath, "r") as f:
            return json.load(f)
    return None


def _count_signals_from_csv(filepath: Path) -> tuple[int, int]:
    """Count total and trade signals from CSV."""
    if not filepath.exists():
        return 0, 0

    total = 0
    trade_signals = 0
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if row.get("trade_long", "").lower() == "true":
                trade_signals += 1

    return total, trade_signals


def _load_signals_from_csv(filepath: Path, limit: int, offset: int, trade_only: bool) -> tuple[List[Dict], int]:
    """Load signals from CSV with pagination."""
    if not filepath.exists():
        return [], 0

    all_signals = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert string values to appropriate types
            signal = dict(row)
            if "score" in signal:
                signal["score"] = float(signal["score"])
            if "confidence" in signal:
                signal["confidence"] = float(signal["confidence"])
            if "evidence_count" in signal:
                signal["evidence_count"] = int(signal["evidence_count"])
            if "trade_long" in signal:
                signal["trade_long"] = signal["trade_long"].lower() == "true"

            if trade_only and not signal.get("trade_long"):
                continue
            all_signals.append(signal)

    total = len(all_signals)
    paginated = all_signals[offset:offset + limit]
    return paginated, total


@router.get("/runs", response_model=RunsList)
async def list_runs(
    limit: int = 20,
    offset: int = 0,
) -> RunsList:
    """
    List all runs.

    Returns summary information for each run.
    """
    # Scan runs directory for run folders
    runs = []

    if not RUNS_DIR.exists():
        return RunsList(runs=[], total=0)

    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue

        config_path = run_dir / "run_config.json"
        config = _load_json_file(config_path)

        if not config:
            continue

        # Load summary if available
        summary_path = run_dir / "summary.json"
        summary = _load_json_file(summary_path)

        # Count signals if summary not available
        total_signals, trade_signals = 0, 0
        if summary:
            total_signals = summary.get("signals_generated", summary.get("total_signals", 0))
            trade_signals = summary.get("trade_signals", 0)
        else:
            signals_path = run_dir / "signals.csv"
            total_signals, trade_signals = _count_signals_from_csv(signals_path)

        # Check if backtest exists
        has_backtest = (run_dir / "backtest_result.json").exists()

        runs.append(
            RunSummary(
                run_id=config.get("run_id", run_dir.name),
                timestamp=config.get("timestamp", ""),
                purpose=config.get("purpose", "unknown"),
                date_range=config.get("date_range", {}),
                total_signals=total_signals,
                trade_signals=trade_signals,
                models=config.get("models", {}),
                has_backtest=has_backtest,
            )
        )

    total = len(runs)
    paginated = runs[offset:offset + limit]

    return RunsList(runs=paginated, total=total)


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str) -> RunDetail:
    """
    Get detailed information for a specific run.
    """
    run_dir = RUNS_DIR / run_id

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Load config
    config_path = run_dir / "run_config.json"
    config = _load_json_file(config_path)

    if not config:
        raise HTTPException(status_code=404, detail=f"Run config not found: {run_id}")

    # Load summary
    summary_path = run_dir / "summary.json"
    summary = _load_json_file(summary_path)

    # Load backtest result
    backtest_path = run_dir / "backtest_result.json"
    backtest_result = _load_json_file(backtest_path)

    return RunDetail(
        run_id=run_id,
        config=config,
        summary=summary,
        backtest_result=backtest_result,
    )


@router.get("/runs/{run_id}/signals")
async def get_run_signals(
    run_id: str,
    limit: int = 100,
    offset: int = 0,
    trade_only: bool = False,
) -> Dict[str, Any]:
    """
    Get signals from a specific run.
    """
    run_dir = RUNS_DIR / run_id

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    signals_path = run_dir / "signals.csv"
    signals, total = _load_signals_from_csv(signals_path, limit, offset, trade_only)

    return {
        "run_id": run_id,
        "signals": signals,
        "total": total,
    }


@router.get("/runs/{run_id}/llm/{event_id}")
async def get_llm_details(run_id: str, event_id: str) -> Dict[str, Any]:
    """
    Get LLM request/response details for a specific event.
    """
    run_dir = RUNS_DIR / run_id

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Load request
    request_path = run_dir / "llm_requests" / f"{event_id}_request.json"
    request_data = _load_json_file(request_path)

    # Load response
    response_path = run_dir / "llm_responses" / f"{event_id}_response.json"
    response_data = _load_json_file(response_path)

    if not request_data and not response_data:
        raise HTTPException(status_code=404, detail=f"LLM data not found for event: {event_id}")

    return {
        "run_id": run_id,
        "event_id": event_id,
        "request": request_data,
        "response": response_data,
    }
