#!/usr/bin/env python3
"""
V9 G2 Daily Signal Generator — Paper Trading Phase 3.

Queries today's earnings events with drop >= 5%, scores with V9 model,
and outputs BUY signals for prob >= threshold.

Usage:
    python3 scripts/daily_signal_v9.py                    # today
    python3 scripts/daily_signal_v9.py --date 2025-10-15  # specific date
    python3 scripts/daily_signal_v9.py --backfill 2025-01-01 2025-12-31

Output:
    signals/YYYY-MM-DD/signals.json
"""

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

# ── Frozen Config ──────────────────────────────────────────────────
FROZEN_CONFIG = {
    "version": "v9_g2_tp10_20260209",
    "model_path": "models/v9_model_20260207_160910.pkl",
    "threshold": 0.58,
    "stop_loss": 0.10,
    "take_profit": 0.10,          # +10% TP exit
    "max_hold_trading_days": 30,   # fallback T+30
    "weight": 0.15,
    "leverage": 2.5,
    "slippage_estimate": 0.001,   # 0.10% per trade
    "half_weight_until": "2026-03-08",  # first month half weight
}

DB_CONFIG = {
    "host": "172.23.22.100",
    "port": 5432,
    "user": "whaleforce",
    "password": "",
    "database": "pead_reversal",
}

FEATURE_NAMES = [
    "drop_1d", "eps_surprise", "eps_beat", "abs_drop",
    "sector_return_20d", "sector_breadth", "spy_above_200dma",
    "drop_x_sector", "sector_x_eps_sign", "beat_dump",
    "value_trap_score", "justified_drop", "sector_divergence",
    "drop_squared", "bear_duration_days", "vix_percentile",
]


def load_model():
    """Load frozen V9 model and verify feature consistency."""
    model_path = Path(__file__).parent.parent / FROZEN_CONFIG["model_path"]
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)

    model = bundle["model"]
    saved_features = bundle["feature_names"]

    assert saved_features == FEATURE_NAMES, (
        f"Feature mismatch!\n"
        f"  Frozen: {FEATURE_NAMES}\n"
        f"  Model:  {saved_features}"
    )

    # Compute model hash for traceability
    with open(model_path, "rb") as f:
        model_hash = hashlib.md5(f.read()).hexdigest()[:12]

    return model, model_hash


def query_day_events(conn, target_date: str):
    """Query earnings events on target_date with drop >= 5%."""
    query = """
    WITH day_earnings AS (
        SELECT
            es.symbol,
            c.name AS company_name,
            c.sector,
            es.date AS event_date,
            es.eps_actual,
            es.eps_estimated,
            CASE
                WHEN es.eps_estimated != 0
                THEN (es.eps_actual - es.eps_estimated) / ABS(es.eps_estimated)
                ELSE 0
            END AS eps_surprise
        FROM earnings_surprises es
        JOIN companies c ON es.symbol = c.symbol
        WHERE es.date = %s
          AND es.eps_actual IS NOT NULL
          AND es.eps_estimated IS NOT NULL
    )
    SELECT
        de.*,
        p0.close AS price_t0,
        p1.close AS price_t1,
        p1.date AS t1_date
    FROM day_earnings de
    LEFT JOIN LATERAL (
        SELECT close, date FROM historical_prices
        WHERE symbol = de.symbol AND date <= de.event_date
        ORDER BY date DESC LIMIT 1
    ) p0 ON true
    LEFT JOIN LATERAL (
        SELECT close, date FROM historical_prices
        WHERE symbol = de.symbol AND date > de.event_date
        ORDER BY date ASC LIMIT 1
    ) p1 ON true
    WHERE p0.close IS NOT NULL
      AND p1.close IS NOT NULL
      AND (p1.close - p0.close) / NULLIF(p0.close, 0) <= -0.05
    ORDER BY de.symbol
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (target_date,))
        return cur.fetchall()


def load_spy_prices(conn):
    """Load SPY close prices for 200DMA and bear duration."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT date, close FROM historical_prices "
            "WHERE symbol = 'SPY' ORDER BY date"
        )
        return {str(row["date"]): float(row["close"]) for row in cur.fetchall()}


def load_vix_prices(conn):
    """Load VIX close prices for percentile."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT date, close FROM historical_prices "
            "WHERE symbol = '^VIX' ORDER BY date"
        )
        rows = cur.fetchall()
        if not rows:
            cur.execute(
                "SELECT date, close FROM historical_prices "
                "WHERE symbol = 'VIX' ORDER BY date"
            )
            rows = cur.fetchall()
        return {str(row["date"]): float(row["close"]) for row in rows}


def compute_spy_200dma_and_duration(spy_prices, event_date):
    """Returns (spy_above_200dma: bool, bear_duration_days: int)."""
    sorted_dates = sorted(spy_prices.keys())
    event_idx = None
    for i, d in enumerate(sorted_dates):
        if d <= event_date:
            event_idx = i
        else:
            break

    if event_idx is None or event_idx < 200:
        return True, 0

    spy_close = spy_prices[sorted_dates[event_idx]]
    prices_200 = [spy_prices[sorted_dates[j]] for j in range(event_idx - 199, event_idx + 1)]
    dma_200 = sum(prices_200) / 200
    above = spy_close > dma_200

    if above:
        return True, 0

    duration = 0
    for k in range(event_idx, max(event_idx - 252, 199), -1):
        close_k = spy_prices[sorted_dates[k]]
        prices_k = [spy_prices[sorted_dates[j]] for j in range(k - 199, k + 1)]
        dma_k = sum(prices_k) / 200
        if close_k < dma_k:
            duration += 1
        else:
            break

    return False, duration


def compute_vix_percentile(vix_prices, event_date):
    """VIX percentile rank over trailing 252 trading days."""
    sorted_dates = sorted(vix_prices.keys())
    event_idx = None
    for i, d in enumerate(sorted_dates):
        if d <= event_date:
            event_idx = i
        else:
            break

    if event_idx is None or event_idx < 60:
        return 0.5

    lookback = min(252, event_idx + 1)
    vix_window = [vix_prices[sorted_dates[j]] for j in range(event_idx - lookback + 1, event_idx + 1)]
    current_vix = vix_prices[sorted_dates[event_idx]]

    rank = sum(1 for v in vix_window if v <= current_vix) / len(vix_window)
    return round(rank, 4)


def compute_sector_features(conn, symbol, event_date):
    """Compute sector return and breadth for a single event."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "data"))
    try:
        from sector_momentum import SectorMomentumCalculator
        calc = SectorMomentumCalculator(DB_CONFIG)
        ret, meta = calc.compute(symbol, event_date)
        return {
            "sector_return_20d": ret,
            "sector_breadth": meta.get("sector_breadth", 0.5),
        }
    except Exception:
        return {"sector_return_20d": 0.0, "sector_breadth": 0.5}


def extract_features(event, spy_above, bear_duration, vix_pctl, sector_feat):
    """Extract 16-feature vector matching V9 model."""
    drop = event["drop_1d"]
    eps = event["eps_surprise"]
    sr = sector_feat.get("sector_return_20d", 0.0)
    sb = sector_feat.get("sector_breadth", 0.5)

    features = {
        "drop_1d": drop,
        "eps_surprise": eps,
        "eps_beat": 1.0 if eps > 0 else 0.0,
        "abs_drop": abs(drop),
        "sector_return_20d": sr,
        "sector_breadth": sb,
        "spy_above_200dma": 1.0 if spy_above else 0.0,
        "drop_x_sector": drop * sr,
        "sector_x_eps_sign": sr * (1.0 if eps > 0 else -1.0),
        "beat_dump": 1.0 if (eps > 0 and drop <= -0.10) else 0.0,
        "value_trap_score": eps * (1.0 if drop > -0.10 else 0.0),
        "justified_drop": 1.0 if (eps < 0 and drop <= -0.12) else 0.0,
        "sector_divergence": 1.0 if (sr > 0.03 and drop > -0.10) else 0.0,
        "drop_squared": drop ** 2,
        "bear_duration_days": min(bear_duration, 200) / 200.0,
        "vix_percentile": vix_pctl,
    }

    return np.array([features.get(f, 0.0) for f in FEATURE_NAMES])


def generate_signals(target_date: str, model, spy_prices, vix_prices, conn=None, fmp=None):
    """Generate signals for a single date. Uses DB (conn) or FMP (fmp)."""
    if fmp is not None:
        events = fmp.query_day_events(target_date)
    else:
        events = query_day_events(conn, target_date)

    if not events:
        return {"date": target_date, "events": 0, "signals": [], "trades": 0}

    signals = []
    for event in events:
        symbol = event["symbol"]
        price_t0 = float(event["price_t0"])
        price_t1 = float(event["price_t1"])
        drop_1d = float(event.get("drop_1d")) if "drop_1d" in event else (price_t1 - price_t0) / price_t0
        eps_surprise = float(event["eps_surprise"]) if event["eps_surprise"] else 0.0

        if fmp is not None:
            sf = fmp.compute_sector_features(symbol, target_date)
        else:
            sf = compute_sector_features(conn, symbol, target_date)
        spy_above, bear_dur = compute_spy_200dma_and_duration(spy_prices, target_date)
        vix_pctl = compute_vix_percentile(vix_prices, target_date)

        e = {"drop_1d": drop_1d, "eps_surprise": eps_surprise}
        X = extract_features(e, spy_above, bear_dur, vix_pctl, sf).reshape(1, -1)
        prob = float(model.predict_proba(X)[0, 1])

        threshold = FROZEN_CONFIG["threshold"]
        action = "BUY" if prob >= threshold else "NO_TRADE"

        # Determine weight (half weight in first month)
        weight = FROZEN_CONFIG["weight"]
        if target_date <= FROZEN_CONFIG["half_weight_until"]:
            weight = weight / 2

        signal = {
            "symbol": symbol,
            "sector": event.get("sector") or "Unknown",
            "event_date": target_date,
            "entry_date": str(event["t1_date"]),
            "price_t0": round(price_t0, 2),
            "price_t1": round(price_t1, 2),
            "drop_1d": round(drop_1d, 4),
            "eps_surprise": round(eps_surprise, 4),
            "ml_prob": round(prob, 4),
            "threshold": threshold,
            "action": action,
            "weight": weight if action == "BUY" else 0,
            "stop_loss": FROZEN_CONFIG["stop_loss"],
            "take_profit": FROZEN_CONFIG["take_profit"],
            "max_hold": FROZEN_CONFIG["max_hold_trading_days"],
            "slippage_estimate": FROZEN_CONFIG["slippage_estimate"],
            "features": {
                "sector_return_20d": round(sf["sector_return_20d"], 5),
                "sector_breadth": round(sf["sector_breadth"], 3),
                "spy_above_200dma": spy_above,
                "bear_duration_days": bear_dur,
                "vix_percentile": round(vix_pctl, 4),
            },
        }
        signals.append(signal)

    trades = [s for s in signals if s["action"] == "BUY"]

    return {
        "date": target_date,
        "events": len(events),
        "signals": signals,
        "trades": len(trades),
        "config": FROZEN_CONFIG,
    }


def save_signals(result, output_dir=None):
    """Save signals to JSON file."""
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "signals" / result["date"]
    else:
        output_dir = Path(output_dir) / result["date"]

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "signals.json"

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    return out_path


# ── Position Tracker (TP10 / SL / MaxHold) ───────────────────────

POSITIONS_FILE = Path(__file__).parent.parent / "signals" / "open_positions.json"


def load_positions():
    """Load open positions from file."""
    if POSITIONS_FILE.exists():
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    return {"open": [], "closed": []}


def save_positions(positions):
    """Save positions to file."""
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2, default=str)


def compute_max_hold_date(entry_date: str, trading_dates: list, hold_days: int = 30) -> str:
    """Compute T+N trading day date from entry_date using actual trading calendar."""
    try:
        idx = trading_dates.index(entry_date)
    except ValueError:
        # Find nearest date >= entry_date
        idx = None
        for i, d in enumerate(trading_dates):
            if d >= entry_date:
                idx = i
                break
        if idx is None:
            # entry_date is beyond all known trading dates — use calendar approx
            dt = datetime.strptime(entry_date, "%Y-%m-%d")
            return (dt + timedelta(days=int(hold_days * 7 / 5 + 5))).strftime("%Y-%m-%d")

    target_idx = idx + hold_days
    if target_idx < len(trading_dates):
        return trading_dates[target_idx]

    # Not enough future trading dates in calendar — approximate remaining
    last_known = trading_dates[-1]
    remaining = target_idx - (len(trading_dates) - 1)
    dt = datetime.strptime(last_known, "%Y-%m-%d")
    return (dt + timedelta(days=int(remaining * 7 / 5 + 2))).strftime("%Y-%m-%d")


def add_position(positions, signal, trading_dates):
    """Add a new BUY signal to open positions."""
    entry_price = signal["price_t1"]
    tp = FROZEN_CONFIG["take_profit"]
    sl = FROZEN_CONFIG["stop_loss"]
    max_hold = FROZEN_CONFIG["max_hold_trading_days"]

    max_hold_date = compute_max_hold_date(signal["entry_date"], trading_dates, max_hold)

    pos = {
        "symbol": signal["symbol"],
        "sector": signal.get("sector", "Unknown"),
        "event_date": signal["event_date"],
        "entry_date": signal["entry_date"],
        "entry_price": entry_price,
        "weight": signal["weight"],
        "prob": signal["ml_prob"],
        "take_profit_price": round(entry_price * (1 + tp), 2),
        "stop_loss_price": round(entry_price * (1 - sl), 2),
        "max_hold_date": max_hold_date,
    }
    positions["open"].append(pos)
    return pos


def check_exits(positions, check_date: str, price_getter):
    """
    Check all open positions for exit conditions.

    Args:
        positions: positions dict with "open" and "closed" lists
        check_date: current date (YYYY-MM-DD)
        price_getter: callable(symbol) -> current close price or None

    Returns:
        list of exit signals
    """
    exits = []
    still_open = []

    for pos in positions["open"]:
        symbol = pos["symbol"]
        current_price = price_getter(symbol)

        if current_price is None:
            still_open.append(pos)
            continue

        entry_price = pos["entry_price"]
        ret = (current_price - entry_price) / entry_price
        exit_reason = None

        # Check TP first (most desirable exit)
        if current_price >= pos["take_profit_price"]:
            exit_reason = "take_profit"
        # Check SL
        elif current_price <= pos["stop_loss_price"]:
            exit_reason = "stop_loss"
        # Check MaxHold
        elif check_date >= pos["max_hold_date"]:
            exit_reason = "max_hold"

        if exit_reason:
            closed = {
                **pos,
                "exit_date": check_date,
                "exit_price": round(current_price, 2),
                "exit_reason": exit_reason,
                "return_pct": round(ret * 100, 2),
                "hold_days_approx": (
                    datetime.strptime(check_date, "%Y-%m-%d") -
                    datetime.strptime(pos["entry_date"], "%Y-%m-%d")
                ).days,
            }
            positions["closed"].append(closed)
            exits.append(closed)
        else:
            still_open.append(pos)

    positions["open"] = still_open
    return exits


def get_trading_dates_from_spy(spy_prices):
    """Extract sorted trading dates from SPY price dict."""
    return sorted(spy_prices.keys())


def main():
    parser = argparse.ArgumentParser(description="V9 G2 TP10 Daily Signal Generator")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                        help="Backfill date range")
    parser.add_argument("--check-exits", action="store_true",
                        help="Check open positions for TP/SL/MaxHold exits")
    parser.add_argument("--init-positions", action="store_true",
                        help="Initialize positions from existing 2026 signal files")
    parser.add_argument("--output-dir", type=str, help="Output directory")
    parser.add_argument("--source", choices=["db", "fmp"], default="db",
                        help="Data source: db (PostgreSQL) or fmp (FMP API)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"V9 G2 Daily Signal Generator — {FROZEN_CONFIG['version']}")
    print("=" * 60)

    # Load model
    model, model_hash = load_model()
    print(f"Model loaded: {FROZEN_CONFIG['model_path']} (hash: {model_hash})")
    print(f"Threshold: {FROZEN_CONFIG['threshold']}, SL: {FROZEN_CONFIG['stop_loss']}")
    print(f"Features: {len(FEATURE_NAMES)} ({', '.join(FEATURE_NAMES[:5])}...)")

    # Load shared data based on source
    conn = None
    fmp = None

    if args.source == "fmp":
        sys.path.insert(0, str(Path(__file__).parent))
        from fmp_data_client import FMPDataClient
        fmp_key = os.environ.get("FMP_API_KEY", "")
        if not fmp_key:
            # Try loading from .env
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("FMP_API_KEY="):
                        fmp_key = line.split("=", 1)[1].strip()
                        break
        fmp = FMPDataClient(api_key=fmp_key)
        print(f"Data source: FMP API (stable)")
        spy_prices = fmp.load_spy_prices()
        vix_prices = fmp.load_vix_prices()
    else:
        conn = psycopg2.connect(**DB_CONFIG)
        print(f"Data source: PostgreSQL ({DB_CONFIG['host']})")
        spy_prices = load_spy_prices(conn)
        vix_prices = load_vix_prices(conn)

    print(f"SPY prices: {len(spy_prices)} days, VIX: {len(vix_prices)} days")

    trading_dates = get_trading_dates_from_spy(spy_prices)

    if args.init_positions:
        # Initialize positions from existing signal files
        print("\n── Initializing positions from existing signals ──")
        positions = {"open": [], "closed": []}
        import glob
        signal_files = sorted(glob.glob(
            str(Path(__file__).parent.parent / "signals" / "2026-*" / "signals.json")
        ))
        for sf in signal_files:
            data = json.load(open(sf))
            for s in data.get("signals", []):
                if s.get("action") == "BUY":
                    add_position(positions, s, trading_dates)
                    print(f"  + {s['entry_date']} {s['symbol']:8s} "
                          f"entry=${s['price_t1']:.2f} "
                          f"TP=${s['price_t1'] * 1.10:.2f} "
                          f"SL=${s['price_t1'] * 0.90:.2f}")
        save_positions(positions)
        print(f"\nInitialized {len(positions['open'])} open positions")
        print(f"Saved to: {POSITIONS_FILE}")

        if conn:
            conn.close()
        return

    if args.check_exits:
        # Check open positions for TP/SL/MaxHold exits
        check_date = args.date or datetime.now().strftime("%Y-%m-%d")
        print(f"\n── Checking exits for {check_date} ──")
        positions = load_positions()
        print(f"Open positions: {len(positions['open'])}")

        if not positions["open"]:
            print("No open positions to check.")
            if conn:
                conn.close()
            return

        # Build price getter
        if fmp is not None:
            def price_getter(symbol):
                prices = fmp._get_symbol_prices(symbol, check_date, lookback_days=3, forward_days=0)
                if not prices:
                    return None
                valid = [d for d in sorted(prices.keys()) if d <= check_date]
                return prices[valid[-1]] if valid else None
        else:
            def price_getter(symbol):
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT close FROM historical_prices "
                        "WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
                        (symbol, check_date)
                    )
                    row = cur.fetchone()
                    return float(row["close"]) if row else None

        exits = check_exits(positions, check_date, price_getter)
        save_positions(positions)

        if exits:
            print(f"\n{'='*60}")
            print(f"EXIT SIGNALS ({len(exits)}):")
            print(f"{'='*60}")
            for ex in exits:
                emoji = {"take_profit": "TP", "stop_loss": "SL", "max_hold": "MH"}[ex["exit_reason"]]
                print(f"  [{emoji}] {ex['symbol']:8s} "
                      f"entry=${ex['entry_price']:.2f} → exit=${ex['exit_price']:.2f} "
                      f"ret={ex['return_pct']:+.1f}% ({ex['hold_days_approx']}d)")
        else:
            print("\nNo exits triggered.")

        # Show remaining open positions and collect summary data
        print(f"\nRemaining open: {len(positions['open'])}")
        pos_summary = []
        for pos in positions["open"]:
            current = price_getter(pos["symbol"])
            if current:
                ret = (current - pos["entry_price"]) / pos["entry_price"] * 100
                print(f"  {pos['symbol']:8s} entry=${pos['entry_price']:.2f} "
                      f"now=${current:.2f} ({ret:+.1f}%) "
                      f"TP=${pos['take_profit_price']:.2f} "
                      f"MaxHold={pos['max_hold_date']}")
                pos_summary.append({
                    "symbol": pos["symbol"],
                    "entry_price": pos["entry_price"],
                    "current_price": round(current, 2),
                    "return_pct": round(ret, 1),
                    "tp_price": pos["take_profit_price"],
                    "max_hold_date": pos["max_hold_date"],
                })

        # Save position summary for LINE notification
        pos_summary.sort(key=lambda x: x["return_pct"], reverse=True)
        summary_data = {
            "date": check_date,
            "open_count": len(positions["open"]),
            "closed_count": len(positions["closed"]),
            "exits": exits,
            "positions": pos_summary,
        }
        summary_path = Path(__file__).parent.parent / "signals" / "position_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary_data, f, indent=2, default=str)
        print(f"Position summary: {summary_path}")

        # Save exit signals to date directory
        if exits:
            exit_dir = Path(__file__).parent.parent / "signals" / check_date
            exit_dir.mkdir(parents=True, exist_ok=True)
            with open(exit_dir / "exits.json", "w") as f:
                json.dump({"date": check_date, "exits": exits}, f, indent=2, default=str)
            print(f"\nExit signals saved to: {exit_dir / 'exits.json'}")

        if conn:
            conn.close()
        return

    if args.backfill:
        # Backfill mode
        start, end = args.backfill
        print(f"\nBackfill mode: {start} to {end}")

        current = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()

        total_events = 0
        total_trades = 0
        days_with_signals = 0
        positions = load_positions()

        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            result = generate_signals(date_str, model, spy_prices, vix_prices,
                                      conn=conn, fmp=fmp)

            if result["events"] > 0:
                out_path = save_signals(result, args.output_dir)
                days_with_signals += 1
                total_events += result["events"]
                total_trades += result["trades"]

                # Auto-add BUY signals to positions
                for s in result["signals"]:
                    if s["action"] == "BUY":
                        add_position(positions, s, trading_dates)

                trades_str = ", ".join(
                    f"{s['symbol']}({s['ml_prob']:.2f})"
                    for s in result["signals"] if s["action"] == "BUY"
                )
                print(f"  {date_str}: {result['events']} events, "
                      f"{result['trades']} trades [{trades_str}]")

            current += timedelta(days=1)

        save_positions(positions)
        print(f"\nBackfill complete: {days_with_signals} days, "
              f"{total_events} events, {total_trades} trades")
        print(f"Open positions: {len(positions['open'])}")

    else:
        # Single date mode
        target_date = args.date or datetime.now().strftime("%Y-%m-%d")
        print(f"\nTarget date: {target_date}")

        result = generate_signals(target_date, model, spy_prices, vix_prices,
                                  conn=conn, fmp=fmp)
        out_path = save_signals(result, args.output_dir)

        print(f"\nEvents found: {result['events']}")
        print(f"Trade signals: {result['trades']}")

        for s in result["signals"]:
            action_str = f"{'BUY' if s['action'] == 'BUY' else 'SKIP':4s}"
            print(f"  {s['symbol']:8s} drop={s['drop_1d']:+.2%} "
                  f"eps={s['eps_surprise']:+.4f} "
                  f"prob={s['ml_prob']:.4f} → {action_str}")

        # Auto-add BUY signals to positions
        positions = load_positions()
        for s in result["signals"]:
            if s["action"] == "BUY":
                pos = add_position(positions, s, trading_dates)
                print(f"  → Position opened: {s['symbol']} "
                      f"TP=${pos['take_profit_price']:.2f} "
                      f"SL=${pos['stop_loss_price']:.2f} "
                      f"MaxHold={pos['max_hold_date']}")
        save_positions(positions)

        print(f"\nOpen positions: {len(positions['open'])}")
        print(f"Saved to: {out_path}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
