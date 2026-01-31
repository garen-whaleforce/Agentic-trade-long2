"""
Runs endpoints.

Provides access to run artifacts and history.
"""

from datetime import date
from typing import List, Optional, Dict, Any
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


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


@router.get("/runs", response_model=RunsList)
async def list_runs(
    limit: int = 20,
    offset: int = 0,
) -> RunsList:
    """
    List all runs.

    Returns summary information for each run.
    """
    # TODO: Implement actual file system reading
    # This is a stub response

    runs = [
        RunSummary(
            run_id="run_20260131_153022_backtest_2017_2025",
            timestamp="2026-01-31T15:30:22Z",
            purpose="backtest",
            date_range={"start": "2017-01-01", "end": "2025-12-31"},
            total_signals=847,
            trade_signals=662,
            models={"batch_score": "gpt-4o-mini"},
            has_backtest=True,
        ),
        RunSummary(
            run_id="run_20260130_091500_tune_2017_2021",
            timestamp="2026-01-30T09:15:00Z",
            purpose="tune",
            date_range={"start": "2017-01-01", "end": "2021-12-31"},
            total_signals=500,
            trade_signals=380,
            models={"batch_score": "gpt-4o-mini"},
            has_backtest=True,
        ),
    ]

    return RunsList(runs=runs[offset : offset + limit], total=len(runs))


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str) -> RunDetail:
    """
    Get detailed information for a specific run.
    """
    # TODO: Implement actual file system reading
    # This is a stub response

    return RunDetail(
        run_id=run_id,
        config={
            "run_id": run_id,
            "timestamp": "2026-01-31T15:30:22Z",
            "purpose": "backtest",
            "date_range": {"start": "2017-01-01", "end": "2025-12-31"},
            "models": {"batch_score": "gpt-4o-mini", "full_audit": "gpt-5-mini"},
            "prompt_versions": {"batch_score": "v1.2.0", "full_audit": "v1.1.0"},
            "thresholds": {
                "score_threshold": 0.70,
                "evidence_min_count": 2,
            },
        },
        summary={
            "total_events": 1000,
            "signals_generated": 847,
            "trade_signals": 662,
            "no_trade_signals": 185,
            "total_cost_usd": 0.85,
            "avg_latency_ms": 1850,
        },
        backtest_result={
            "backtest_id": "bt_20260131_abc123",
            "performance": {
                "cagr": 0.385,
                "sharpe_ratio": 2.15,
                "win_rate": 0.782,
                "max_drawdown": -0.153,
            },
            "trade_stats": {
                "total_trades": 662,
                "trades_per_year": 74,
            },
        },
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
    # TODO: Implement actual CSV reading
    # This is a stub response

    signals = [
        {
            "event_id": "evt_aapl_2024q1",
            "symbol": "AAPL",
            "event_date": "2024-01-25",
            "score": 0.82,
            "trade_long": True,
            "confidence": 0.78,
            "evidence_count": 3,
        },
        {
            "event_id": "evt_msft_2024q2",
            "symbol": "MSFT",
            "event_date": "2024-01-30",
            "score": 0.45,
            "trade_long": False,
            "confidence": 0.42,
            "evidence_count": 1,
            "no_trade_reason": "score_below_threshold",
        },
    ]

    if trade_only:
        signals = [s for s in signals if s.get("trade_long")]

    return {
        "run_id": run_id,
        "signals": signals[offset : offset + limit],
        "total": len(signals),
    }


@router.get("/runs/{run_id}/llm/{event_id}")
async def get_llm_details(run_id: str, event_id: str) -> Dict[str, Any]:
    """
    Get LLM request/response details for a specific event.
    """
    # TODO: Implement actual file reading
    # This is a stub response

    return {
        "run_id": run_id,
        "event_id": event_id,
        "request": {
            "model": "gpt-4o-mini",
            "prompt_template_id": "batch_score_v1.2.0",
            "prompt_hash": "sha256:abc123def456",
            "rendered_prompt": "Analyze the following earnings call transcript...",
            "parameters": {
                "temperature": 0,
                "max_tokens": 500,
            },
        },
        "response": {
            "raw_output": {
                "score": 0.82,
                "trade_candidate": True,
                "evidence_count": 3,
                "evidence_snippets": [
                    {"quote": "We expect 15-18% growth", "speaker": "CFO"},
                ],
            },
            "token_usage": {"input": 2500, "output": 350, "total": 2850},
            "cost_usd": 0.00058,
            "latency_ms": 1850,
        },
    }
