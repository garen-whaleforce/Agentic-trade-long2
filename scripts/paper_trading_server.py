#!/usr/bin/env python3
"""
Lightweight Paper Trading API server — serves dashboard endpoints only.
Reads from JSON/YAML files produced by daily_signal_v9.py.

Usage:
    python3 scripts/paper_trading_server.py
    # => http://localhost:8000
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIGNALS_DIR = PROJECT_ROOT / "signals"
POSITIONS_FILE = SIGNALS_DIR / "open_positions.json"
CONFIG_FILE = PROJECT_ROOT / "configs" / "v9_g2_frozen.yaml"
LOGS_DIR = PROJECT_ROOT / "logs"
LINE_USERS_FILE = PROJECT_ROOT / "configs" / "line_users.json"

LINE_CHANNEL_TOKEN = os.environ.get("LINE_CHANNEL_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

logger = logging.getLogger("paper_trading")

app = FastAPI(title="Contrarian Alpha — Paper Trading API")


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

    # Find latest log file matching daily_signal_*.log pattern
    if LOGS_DIR.exists():
        log_files = sorted(LOGS_DIR.glob("daily_signal_*.log"))
        if log_files:
            latest_log = log_files[-1]
            stat = latest_log.stat()
            last_log_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
            with open(latest_log) as f:
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


# ---------------------------------------------------------------------------
# LINE Webhook — auto-register users who follow or message the bot
# ---------------------------------------------------------------------------

def _load_line_users() -> list[dict]:
    if not LINE_USERS_FILE.exists():
        return []
    with open(LINE_USERS_FILE) as f:
        return json.load(f)


def _save_line_users(users: list[dict]):
    LINE_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINE_USERS_FILE, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _verify_line_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET:
        return True  # skip verification if secret not configured
    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256
    ).digest()
    import base64
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


async def _reply_line(reply_token: str, text: str):
    if not LINE_CHANNEL_TOKEN:
        logger.warning("LINE_CHANNEL_TOKEN not set, cannot reply")
        return
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}",
            },
            json={
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": text}],
            },
        )
        logger.info(f"LINE reply: {resp.status_code} {resp.text}")


@app.post("/api/line/webhook")
async def line_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("x-line-signature", "")

    if LINE_CHANNEL_SECRET and not _verify_line_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(body)
    events = payload.get("events", [])

    for event in events:
        event_type = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")
        reply_token = event.get("replyToken")

        if not user_id:
            continue

        if event_type in ("follow", "message"):
            users = _load_line_users()
            existing_ids = {u["user_id"] for u in users}

            if user_id not in existing_ids:
                users.append({
                    "user_id": user_id,
                    "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": event_type,
                })
                _save_line_users(users)
                logger.info(f"LINE user registered: {user_id} via {event_type}")

                if reply_token:
                    await _reply_line(
                        reply_token,
                        "歡迎訂閱 Contrarian Alpha 每日信號通知！\n"
                        "每個交易日收盤後，你會收到當日交易信號與持倉更新。",
                    )
            else:
                if reply_token and event_type == "message":
                    await _reply_line(reply_token, "你已經訂閱囉，每個交易日都會推送通知！")

    return {"status": "ok"}


@app.get("/api/line/users")
def list_line_users():
    users = _load_line_users()
    return {"users": users, "count": len(users)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
