#!/usr/bin/env python3
"""
Lightweight Paper Trading API server — serves dashboard endpoints only.
Reads from JSON/YAML files produced by daily_signal_v9.py.

Usage:
    python3 scripts/paper_trading_server.py
    # => http://localhost:8000
"""

import json
import os
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIGNALS_DIR = PROJECT_ROOT / "signals"
POSITIONS_FILE = SIGNALS_DIR / "open_positions.json"
CONFIG_FILE = PROJECT_ROOT / "configs" / "v9_g2_frozen.yaml"
LOG_FILE = PROJECT_ROOT / "logs" / "daily_signal.log"

app = FastAPI(title="Goshawk Alpha — Paper Trading API")


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:3001", "http://localhost:3002",
        "http://localhost:3400", "http://localhost:13400", "http://localhost:13410",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_positions() -> dict:
    if not POSITIONS_FILE.exists():
        return {"open": [], "closed": []}
    with open(POSITIONS_FILE) as f:
        return json.load(f)


@app.get("/api/paper-trading/summary")
def get_summary():
    data = _load_positions()
    open_pos = data.get("open", [])
    closed_pos = data.get("closed", [])

    exit_reasons = {}
    closed_returns = []
    for p in closed_pos:
        reason = p.get("exit_reason", "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        if "return_pct" in p:
            closed_returns.append(p["return_pct"])

    avg_closed_return = (
        sum(closed_returns) / len(closed_returns) if closed_returns else 0.0
    )
    total_weight = sum(p.get("weight", 0) for p in open_pos)

    return {
        "open_count": len(open_pos),
        "closed_count": len(closed_pos),
        "total_positions": len(open_pos) + len(closed_pos),
        "total_open_weight": round(total_weight, 4),
        "avg_closed_return_pct": round(avg_closed_return, 2),
        "exit_reasons": exit_reasons,
        "tp_hit_rate": round(
            exit_reasons.get("take_profit", 0) / max(len(closed_pos), 1), 2
        ),
    }


@app.get("/api/paper-trading/positions")
def get_positions(status: str = Query(None)):
    data = _load_positions()
    if status == "open":
        return {"positions": data.get("open", []), "status_filter": "open"}
    elif status == "closed":
        return {"positions": data.get("closed", []), "status_filter": "closed"}
    else:
        return {"open": data.get("open", []), "closed": data.get("closed", [])}


@app.get("/api/paper-trading/signals/dates")
def get_signal_dates():
    if not SIGNALS_DIR.exists():
        return {"dates": [], "count": 0}
    dates = []
    for d in sorted(SIGNALS_DIR.iterdir()):
        if d.is_dir() and (d / "signals.json").exists():
            dates.append(d.name)
    return {"dates": dates, "count": len(dates)}


@app.get("/api/paper-trading/signals")
def get_signals(date: str = Query(...)):
    signal_file = SIGNALS_DIR / date / "signals.json"
    if not signal_file.exists():
        raise HTTPException(status_code=404, detail=f"No signals for {date}")
    with open(signal_file) as f:
        return json.load(f)


@app.get("/api/paper-trading/config")
def get_config():
    if not CONFIG_FILE.exists():
        raise HTTPException(status_code=404, detail="Frozen config not found")
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


@app.get("/api/paper-trading/health")
def get_health():
    last_log_time = None
    last_log_line = None
    if LOG_FILE.exists():
        stat = LOG_FILE.stat()
        last_log_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
        with open(LOG_FILE) as f:
            lines = f.readlines()
            for line in reversed(lines):
                if line.strip():
                    last_log_line = line.strip()
                    break

    signal_days = 0
    if SIGNALS_DIR.exists():
        signal_days = sum(
            1 for d in SIGNALS_DIR.iterdir()
            if d.is_dir() and (d / "signals.json").exists()
        )

    return {
        "last_log_time": last_log_time,
        "last_log_line": last_log_line,
        "signal_days": signal_days,
        "positions_file_exists": POSITIONS_FILE.exists(),
        "config_file_exists": CONFIG_FILE.exists(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
