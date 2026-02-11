#!/usr/bin/env python3
"""
V10 Combined Daily Signal Generator — Paper Trading.

Extends V9 with 9 new features:
  - 6 candle features (gap_pct, intraday_ret, close_pos, range_pct, range_over_atr, rel_vol)
  - 3 company DNA features (hist_bounce_rate, hist_avg_return, n_prior_events)

Usage:
    python3 scripts/daily_signal_v10.py                          # today (FMP)
    python3 scripts/daily_signal_v10.py --source fmp --date 2026-02-11
    python3 scripts/daily_signal_v10.py --source db --backfill 2025-10-01 2025-12-31
    python3 scripts/daily_signal_v10.py --source fmp --check-exits --date 2026-02-11

Output:
    signals/YYYY-MM-DD/signals.json
"""

import argparse
import hashlib
import json
import os
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

# ── Frozen Config ──────────────────────────────────────────────────
FROZEN_CONFIG = {
    "version": "v10_combined_tp10_20260211",
    "model_path": "models/v10_combined_model_20260211_141639.pkl",
    "threshold": 0.58,
    "stop_loss": 0.10,
    "take_profit": 0.10,          # +10% TP exit
    "max_hold_trading_days": 30,   # fallback T+30
    "weight": 0.15,
    "leverage": 2.5,
    "slippage_estimate": 0.001,   # 0.10% per trade
    "half_weight_until": None,    # V10 inherits V9 paper trading history
}

DB_CONFIG = {
    "host": "172.23.22.100",
    "port": 5432,
    "user": "whaleforce",
    "password": "",
    "database": "pead_reversal",
}

# 25 features: V9 16 + candle 6 + company_dna 3
FEATURE_NAMES = [
    # V9 base (16)
    "drop_1d", "eps_surprise", "eps_beat", "abs_drop",
    "sector_return_20d", "sector_breadth", "spy_above_200dma",
    "drop_x_sector", "sector_x_eps_sign", "beat_dump",
    "value_trap_score", "justified_drop", "sector_divergence",
    "drop_squared", "bear_duration_days", "vix_percentile",
    # Candle (6)
    "gap_pct", "intraday_ret", "close_pos", "range_pct",
    "range_over_atr", "rel_vol",
    # Company DNA (3)
    "hist_bounce_rate", "hist_avg_return", "n_prior_events",
]

CANDLE_FEATURE_NAMES = [
    "gap_pct", "intraday_ret", "close_pos", "range_pct",
    "range_over_atr", "rel_vol",
]

DNA_FEATURE_NAMES = [
    "hist_bounce_rate", "hist_avg_return", "n_prior_events",
]

# ── Company DNA Cache ─────────────────────────────────────────────
DNA_CACHE_PATH = Path(__file__).parent.parent / "signals" / "company_dna_cache.json"
_dna_cache = None

DNA_DEFAULTS = {
    "hist_bounce_rate": 0.5,
    "hist_avg_return": 0.03,
    "n_prior_events": 0,
}


def load_dna_cache():
    """Load company DNA cache from JSON (singleton)."""
    global _dna_cache
    if _dna_cache is not None:
        return _dna_cache

    if DNA_CACHE_PATH.exists():
        with open(DNA_CACHE_PATH) as f:
            _dna_cache = json.load(f)
        n_symbols = len([k for k in _dna_cache if k != "_meta"])
        print(f"DNA cache loaded: {n_symbols} symbols")
    else:
        print(f"WARNING: DNA cache not found at {DNA_CACHE_PATH}, using defaults")
        _dna_cache = {}

    return _dna_cache


def get_dna_features(symbol: str) -> dict:
    """Get company DNA features for a symbol from cache."""
    cache = load_dna_cache()
    dna = cache.get(symbol, DNA_DEFAULTS)
    if isinstance(dna, dict) and "hist_bounce_rate" in dna:
        return {
            "hist_bounce_rate": dna["hist_bounce_rate"],
            "hist_avg_return": dna["hist_avg_return"],
            "n_prior_events": min(dna.get("n_prior_events", 0), 10) / 10.0,
        }
    return {
        "hist_bounce_rate": DNA_DEFAULTS["hist_bounce_rate"],
        "hist_avg_return": DNA_DEFAULTS["hist_avg_return"],
        "n_prior_events": 0.0,
    }


# ── Candle Features ───────────────────────────────────────────────

def _empty_candle():
    return {
        "gap_pct": 0.0, "intraday_ret": 0.0, "close_pos": 0.5,
        "range_pct": 0.0, "range_over_atr": 1.0, "rel_vol": 1.0,
    }


def compute_candle_features(event: dict, ohlcv: dict) -> dict:
    """
    Compute 6 candle features from OHLCV data.
    ohlcv: {date_str: {open, high, low, close, volume}} for the symbol.
    """
    event_date = event["event_date"]
    t1_date = event.get("t1_date", "") or event.get("entry_date", "")

    if not ohlcv or not t1_date:
        return _empty_candle()

    # Find T0 data (on or before event_date)
    t0_data = ohlcv.get(event_date)
    if t0_data is None:
        all_dates = sorted(ohlcv.keys())
        pre = [d for d in all_dates if d <= event_date]
        if pre:
            t0_data = ohlcv[pre[-1]]
        else:
            return _empty_candle()

    t1_data = ohlcv.get(t1_date)
    if t1_data is None:
        return _empty_candle()

    feats = {}

    # Gap
    t0_close = t0_data["close"]
    t1_open = t1_data["open"]
    feats["gap_pct"] = (t1_open / t0_close - 1) if t0_close > 0 else 0.0

    # Intraday return
    feats["intraday_ret"] = (t1_data["close"] / t1_open - 1) if t1_open > 0 else 0.0

    # Close position within bar
    bar_range = t1_data["high"] - t1_data["low"]
    if bar_range > 0:
        feats["close_pos"] = (t1_data["close"] - t1_data["low"]) / bar_range
    else:
        feats["close_pos"] = 0.5

    # Range as pct of open
    feats["range_pct"] = bar_range / t1_open if t1_open > 0 else 0.0

    # Range over ATR (need 20 trading days before T1)
    all_dates = sorted(ohlcv.keys())
    t1_idx = all_dates.index(t1_date) if t1_date in all_dates else -1
    if t1_idx >= 20:
        atr_sum = 0.0
        for i in range(t1_idx - 20, t1_idx):
            d = all_dates[i]
            atr_sum += ohlcv[d]["high"] - ohlcv[d]["low"]
        avg_atr = atr_sum / 20
        feats["range_over_atr"] = bar_range / avg_atr if avg_atr > 0 else 1.0
    else:
        feats["range_over_atr"] = 1.0

    # Relative volume
    t1_vol = t1_data.get("volume", 0)
    if t1_idx >= 20:
        vol_sum = sum(ohlcv[all_dates[i]].get("volume", 0) for i in range(t1_idx - 20, t1_idx))
        avg_vol = vol_sum / 20
        feats["rel_vol"] = t1_vol / avg_vol if avg_vol > 0 else 1.0
    else:
        feats["rel_vol"] = 1.0

    return feats


# ── OHLCV Loading ─────────────────────────────────────────────────

def load_ohlcv_from_db(conn, symbol: str) -> dict:
    """Load OHLCV prices for a symbol from DB."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT date, open, high, low, close, volume "
            "FROM historical_prices WHERE symbol = %s ORDER BY date",
            (symbol,)
        )
        rows = cur.fetchall()
    return {
        str(row["date"]): {
            "open": float(row["open"]) if row["open"] else 0.0,
            "high": float(row["high"]) if row["high"] else 0.0,
            "low": float(row["low"]) if row["low"] else 0.0,
            "close": float(row["close"]) if row["close"] else 0.0,
            "volume": float(row["volume"]) if row["volume"] else 0.0,
        }
        for row in rows
    }


# ── Model Loading ─────────────────────────────────────────────────

def load_model():
    """Load frozen V10 model and verify feature consistency."""
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


# ── DB Queries (same as V9) ──────────────────────────────────────

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


# ── Feature Computation (same as V9 for base 16) ────────────────

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


# ── V10 Feature Extraction (25 features) ─────────────────────────

def extract_features(event, spy_above, bear_duration, vix_pctl, sector_feat,
                     candle_feat, dna_feat):
    """Extract 25-feature vector for V10 model."""
    drop = event["drop_1d"]
    eps = event["eps_surprise"]
    sr = sector_feat.get("sector_return_20d", 0.0)
    sb = sector_feat.get("sector_breadth", 0.5)

    features = {
        # V9 base (16)
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
        # Candle (6)
        "gap_pct": candle_feat.get("gap_pct", 0.0),
        "intraday_ret": candle_feat.get("intraday_ret", 0.0),
        "close_pos": candle_feat.get("close_pos", 0.5),
        "range_pct": candle_feat.get("range_pct", 0.0),
        "range_over_atr": candle_feat.get("range_over_atr", 1.0),
        "rel_vol": candle_feat.get("rel_vol", 1.0),
        # Company DNA (3)
        "hist_bounce_rate": dna_feat.get("hist_bounce_rate", 0.5),
        "hist_avg_return": dna_feat.get("hist_avg_return", 0.03),
        "n_prior_events": dna_feat.get("n_prior_events", 0.0),
    }

    return np.array([features.get(f, 0.0) for f in FEATURE_NAMES])


# ── Signal Generation ─────────────────────────────────────────────

def generate_signals(target_date: str, model, spy_prices, vix_prices,
                     conn=None, fmp=None):
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
        t1_date = str(event.get("t1_date", ""))

        # Sector features
        if fmp is not None:
            sf = fmp.compute_sector_features(symbol, target_date)
        else:
            sf = compute_sector_features(conn, symbol, target_date)
        spy_above, bear_dur = compute_spy_200dma_and_duration(spy_prices, target_date)
        vix_pctl = compute_vix_percentile(vix_prices, target_date)

        # Candle features (V10 new)
        if fmp is not None:
            sym_ohlcv = fmp.load_ohlcv_prices(symbol, from_date="2016-01-01")
        else:
            sym_ohlcv = load_ohlcv_from_db(conn, symbol)

        candle_event = {
            "symbol": symbol,
            "event_date": target_date,
            "t1_date": t1_date,
        }
        candle_feat = compute_candle_features(candle_event, sym_ohlcv)

        # Company DNA features (V10 new)
        dna_feat = get_dna_features(symbol)

        e = {"drop_1d": drop_1d, "eps_surprise": eps_surprise}
        X = extract_features(e, spy_above, bear_dur, vix_pctl, sf,
                             candle_feat, dna_feat).reshape(1, -1)
        prob = float(model.predict_proba(X)[0, 1])

        threshold = FROZEN_CONFIG["threshold"]
        action = "BUY" if prob >= threshold else "NO_TRADE"

        # Determine weight
        weight = FROZEN_CONFIG["weight"]
        hw_until = FROZEN_CONFIG.get("half_weight_until")
        if hw_until and target_date <= hw_until:
            weight = weight / 2

        signal = {
            "symbol": symbol,
            "sector": event.get("sector") or "Unknown",
            "event_date": target_date,
            "entry_date": t1_date,
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
                "gap_pct": round(candle_feat.get("gap_pct", 0.0), 4),
                "close_pos": round(candle_feat.get("close_pos", 0.5), 4),
                "rel_vol": round(candle_feat.get("rel_vol", 1.0), 2),
                "hist_bounce_rate": round(dna_feat.get("hist_bounce_rate", 0.5), 4),
                "n_prior_events": round(dna_feat.get("n_prior_events", 0.0), 2),
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
        idx = None
        for i, d in enumerate(trading_dates):
            if d >= entry_date:
                idx = i
                break
        if idx is None:
            dt = datetime.strptime(entry_date, "%Y-%m-%d")
            return (dt + timedelta(days=int(hold_days * 7 / 5 + 5))).strftime("%Y-%m-%d")

    target_idx = idx + hold_days
    if target_idx < len(trading_dates):
        return trading_dates[target_idx]

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
    """Check all open positions for exit conditions."""
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

        if current_price >= pos["take_profit_price"]:
            exit_reason = "take_profit"
        elif current_price <= pos["stop_loss_price"]:
            exit_reason = "stop_loss"
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


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="V10 Combined Daily Signal Generator")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                        help="Backfill date range")
    parser.add_argument("--check-exits", action="store_true",
                        help="Check open positions for TP/SL/MaxHold exits")
    parser.add_argument("--init-positions", action="store_true",
                        help="Initialize positions from existing 2026 signal files")
    parser.add_argument("--output-dir", type=str, help="Output directory")
    parser.add_argument("--source", choices=["db", "fmp"], default="fmp",
                        help="Data source: db (PostgreSQL) or fmp (FMP API)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"V10 Combined Daily Signal Generator — {FROZEN_CONFIG['version']}")
    print("=" * 60)

    # Load model
    model, model_hash = load_model()
    print(f"Model loaded: {FROZEN_CONFIG['model_path']} (hash: {model_hash})")
    print(f"Threshold: {FROZEN_CONFIG['threshold']}, Features: {len(FEATURE_NAMES)}")
    print(f"  V9 base: 16, Candle: 6, DNA: 3")

    # Load DNA cache
    load_dna_cache()

    # Load shared data based on source
    conn = None
    fmp = None

    if args.source == "fmp":
        sys.path.insert(0, str(Path(__file__).parent))
        from fmp_data_client import FMPDataClient
        fmp_key = os.environ.get("FMP_API_KEY", "")
        if not fmp_key:
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
        if conn:
            conn.close()
        return

    if args.check_exits:
        check_date = args.date or datetime.now().strftime("%Y-%m-%d")
        print(f"\n── Checking exits for {check_date} ──")
        positions = load_positions()
        print(f"Open positions: {len(positions['open'])}")

        if not positions["open"]:
            print("No open positions to check.")
            if conn:
                conn.close()
            return

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
