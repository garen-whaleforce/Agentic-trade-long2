#!/usr/bin/env python3
"""
Train V10 Combined model (25 features) and produce company DNA cache.

Features: V9 16 + candle 6 + company_dna 3 = 25
Training: 2017-2023 (same as API validation)
Output:
  - models/v10_combined_model_YYYYMMDD_HHMMSS.pkl
  - signals/company_dna_cache.json

Usage:
    python3 scripts/train_v10_combined.py
"""

import json
import pickle
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from sklearn.ensemble import GradientBoostingClassifier

sys.path.insert(0, str(Path(__file__).parent))
from train_ml_v9 import (
    query_all_events, load_spy_prices, load_vix_prices,
    compute_spy_200dma_and_duration, compute_vix_percentile,
    compute_sector_features_batch, FEATURE_NAMES as V9_FEATURE_NAMES,
    LABEL_THRESHOLD,
)
from v10_feature_research import (
    load_ohlcv_prices, compute_candle_features, compute_company_dna_features,
    CANDLE_FEATURES, COMPANY_DNA_FEATURES,
)

DB_CONFIG = {
    "host": "172.23.22.100", "port": 5432,
    "user": "whaleforce", "password": "", "dbname": "pead_reversal",
}

MODELS_DIR = Path(__file__).parent.parent / "models"
SIGNALS_DIR = Path(__file__).parent.parent / "signals"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

# V10 Combined feature names: V9 16 + candle 6 + company_dna 3 = 25
V10_FEATURE_NAMES = list(V9_FEATURE_NAMES) + CANDLE_FEATURES + COMPANY_DNA_FEATURES

# Training config (identical to API validation)
TRAIN_YEARS = (2017, 2023)  # inclusive
GB_PARAMS = {
    "n_estimators": 100,
    "max_depth": 3,
    "learning_rate": 0.08,
    "subsample": 0.8,
    "random_state": 42,
}


def build_v9_features(event, sector_features, spy_prices, vix_prices):
    """Build V9 base feature dict for an event."""
    key = f"{event['symbol']}_{event['event_date']}"
    sf = sector_features.get(key, {"sector_return_20d": 0.0, "sector_breadth": 0.5})
    spy_above, bear_dur = compute_spy_200dma_and_duration(spy_prices, event["event_date"])
    vix_pctl = compute_vix_percentile(vix_prices, event["event_date"])

    return {
        "drop_1d": event["drop_1d"],
        "eps_surprise": event["eps_surprise"],
        "eps_beat": 1.0 if event["eps_surprise"] > 0 else 0.0,
        "abs_drop": abs(event["drop_1d"]),
        "sector_return_20d": sf.get("sector_return_20d", 0.0),
        "sector_breadth": sf.get("sector_breadth", 0.5),
        "spy_above_200dma": 1.0 if spy_above else 0.0,
        "drop_x_sector": event["drop_1d"] * sf.get("sector_return_20d", 0.0),
        "sector_x_eps_sign": sf.get("sector_return_20d", 0.0) * (1.0 if event["eps_surprise"] > 0 else -1.0),
        "beat_dump": 1.0 if (event["eps_surprise"] > 0 and event["drop_1d"] <= -0.10) else 0.0,
        "value_trap_score": event["eps_surprise"] * (1.0 if event["drop_1d"] > -0.10 else 0.0),
        "justified_drop": 1.0 if (event["eps_surprise"] < 0 and event["drop_1d"] <= -0.12) else 0.0,
        "sector_divergence": 1.0 if (sf.get("sector_return_20d", 0.0) > 0.03 and event["drop_1d"] > -0.10) else 0.0,
        "drop_squared": event["drop_1d"] ** 2,
        "bear_duration_days": min(bear_dur, 200) / 200.0,
        "vix_percentile": vix_pctl,
    }


def build_company_dna_cache(events, dna_features):
    """
    Build company DNA cache for production use.
    Uses all historical data (up to latest event) for each symbol.

    Returns: {symbol: {hist_bounce_rate, hist_avg_return, n_prior_events}}
    """
    sorted_events = sorted(events, key=lambda e: e["event_date"])
    company_history = defaultdict(list)

    all_returns = [e["return_30d"] for e in sorted_events]
    global_bounce_rate = float(np.mean([1 if r > LABEL_THRESHOLD else 0 for r in all_returns]))
    global_avg_return = float(np.mean(all_returns))
    prior_weight = 3

    for e in sorted_events:
        company_history[e["symbol"]].append(e["return_30d"])

    cache = {
        "_meta": {
            "global_bounce_rate": global_bounce_rate,
            "global_avg_return": global_avg_return,
            "prior_weight": prior_weight,
            "n_events": len(sorted_events),
            "n_symbols": len(company_history),
            "label_threshold": LABEL_THRESHOLD,
            "data_range": f"{sorted_events[0]['event_date']} to {sorted_events[-1]['event_date']}",
            "generated_at": datetime.now().isoformat(),
        }
    }

    for symbol, returns in company_history.items():
        n = len(returns)
        raw_bounce = float(np.mean([1 if r > LABEL_THRESHOLD else 0 for r in returns]))
        raw_avg = float(np.mean(returns))
        shrunk_bounce = (n * raw_bounce + prior_weight * global_bounce_rate) / (n + prior_weight)
        shrunk_avg = (n * raw_avg + prior_weight * global_avg_return) / (n + prior_weight)

        cache[symbol] = {
            "hist_bounce_rate": round(shrunk_bounce, 6),
            "hist_avg_return": round(shrunk_avg, 6),
            "n_prior_events": n,
        }

    return cache


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 70)
    print(f"V10 Combined Model Training — {timestamp}")
    print("=" * 70)
    print(f"Features: {len(V10_FEATURE_NAMES)} (V9 {len(V9_FEATURE_NAMES)} + "
          f"candle {len(CANDLE_FEATURES)} + DNA {len(COMPANY_DNA_FEATURES)})")
    print(f"Training years: {TRAIN_YEARS[0]}-{TRAIN_YEARS[1]}")
    print(f"Label threshold: return_30d > {LABEL_THRESHOLD:.1%}")
    print()

    # Load data
    print("Loading data from DB...")
    conn = psycopg2.connect(**DB_CONFIG)
    events = query_all_events(conn, "2017-01-01", "2025-12-31")
    spy_prices = load_spy_prices(conn)
    vix_prices = load_vix_prices(conn)
    sector_features = compute_sector_features_batch(events, conn)
    ohlcv = load_ohlcv_prices(conn)
    conn.close()
    print(f"Loaded {len(events)} events, {len(ohlcv)} symbols with OHLCV")

    # Compute company DNA features (walk-forward, no lookahead)
    print("\nComputing company DNA features...")
    dna_features = compute_company_dna_features(events)
    print(f"DNA features computed for {len(dna_features)} events")

    # Build feature matrix
    print(f"\nBuilding feature matrix ({len(V10_FEATURE_NAMES)} features)...")
    X_all, y_all, event_years = [], [], []

    for e in events:
        feats = build_v9_features(e, sector_features, spy_prices, vix_prices)
        feats.update(compute_candle_features(e, ohlcv))

        key = f"{e['symbol']}_{e['event_date']}"
        dna = dna_features.get(key, {
            "hist_bounce_rate": 0.5, "hist_avg_return": 0.03, "n_prior_events": 0,
        })
        feats.update(dna)
        feats["n_prior_events"] = min(feats["n_prior_events"], 10) / 10.0

        X_all.append([feats.get(f, 0.0) for f in V10_FEATURE_NAMES])
        y_all.append(1 if e["return_30d"] > LABEL_THRESHOLD else 0)
        event_years.append(int(e["event_date"][:4]))

    X_all = np.array(X_all)
    y_all = np.array(y_all)
    event_years = np.array(event_years)

    n_good = int(y_all.sum())
    n_bad = len(y_all) - n_good
    print(f"Label distribution: GOOD={n_good} ({100*n_good/len(y_all):.1f}%), "
          f"BAD={n_bad} ({100*n_bad/len(y_all):.1f}%)")

    # Train final model on 2017-2023
    train_mask = (event_years >= TRAIN_YEARS[0]) & (event_years <= TRAIN_YEARS[1])
    n_train = int(train_mask.sum())
    print(f"\nTraining on {n_train} events ({TRAIN_YEARS[0]}-{TRAIN_YEARS[1]})...")

    model = GradientBoostingClassifier(**GB_PARAMS)
    model.fit(X_all[train_mask], y_all[train_mask])

    # Feature importance
    importances = dict(zip(V10_FEATURE_NAMES, model.feature_importances_))
    sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    print(f"\nTop 15 feature importances:")
    for fn, imp in sorted_imp[:15]:
        is_new = fn not in V9_FEATURE_NAMES
        marker = " [NEW]" if is_new else ""
        print(f"  {fn}: {imp:.4f}{marker}")

    # Score all events to verify
    print(f"\nScoring all {len(events)} events...")
    probs = model.predict_proba(X_all)[:, 1]
    n_above = int((probs >= 0.58).sum())
    print(f"Trades above threshold 0.58: {n_above}")

    # Walk-forward separation check
    print(f"\nWalk-forward separation check:")
    for test_year in range(2022, 2026):
        mask = event_years == test_year
        if mask.sum() == 0:
            continue
        trade_mask = mask & (probs >= 0.58)
        skip_mask = mask & (probs < 0.58)
        if trade_mask.sum() > 0 and skip_mask.sum() > 0:
            trade_ret = np.mean([events[i]["return_30d"] for i in np.where(trade_mask)[0]])
            skip_ret = np.mean([events[i]["return_30d"] for i in np.where(skip_mask)[0]])
            sep = trade_ret - skip_ret
            print(f"  {test_year}: Trade avg={trade_ret:.2%}, Skip avg={skip_ret:.2%}, "
                  f"Sep={sep:+.2%} ({'OK' if sep > 0 else 'WARN'})")

    # Save model bundle
    model_path = MODELS_DIR / f"v10_combined_model_{timestamp}.pkl"
    bundle = {
        "model": model,
        "feature_names": V10_FEATURE_NAMES,
        "version": f"v10_combined_{timestamp}",
        "train_years": TRAIN_YEARS,
        "gb_params": GB_PARAMS,
        "label_threshold": LABEL_THRESHOLD,
        "n_features": len(V10_FEATURE_NAMES),
        "n_train_events": n_train,
        "n_total_events": len(events),
        "feature_importance": {k: round(v, 6) for k, v in sorted_imp},
        "trained_at": datetime.now().isoformat(),
    }
    with open(model_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"\nModel saved: {model_path}")
    print(f"  Features: {len(V10_FEATURE_NAMES)}")
    print(f"  Version: {bundle['version']}")

    # Build and save company DNA cache
    print(f"\nBuilding company DNA cache...")
    dna_cache = build_company_dna_cache(events, dna_features)
    cache_path = SIGNALS_DIR / "company_dna_cache.json"
    with open(cache_path, "w") as f:
        json.dump(dna_cache, f, indent=2)
    n_symbols = len([k for k in dna_cache if k != "_meta"])
    print(f"DNA cache saved: {cache_path}")
    print(f"  Symbols: {n_symbols}")
    print(f"  Global bounce rate: {dna_cache['_meta']['global_bounce_rate']:.3f}")

    # Summary
    print(f"\n{'='*70}")
    print(f"TRAINING COMPLETE")
    print(f"{'='*70}")
    print(f"Model: {model_path}")
    print(f"DNA cache: {cache_path}")
    print(f"Features: {len(V10_FEATURE_NAMES)}")
    print(f"  V9 base: {V9_FEATURE_NAMES}")
    print(f"  Candle:  {CANDLE_FEATURES}")
    print(f"  DNA:     {COMPANY_DNA_FEATURES}")
    print(f"\nNext step: update configs/v10_combined_frozen.yaml with model path")


if __name__ == "__main__":
    main()
