#!/usr/bin/env python3
"""
Format a rich LINE notification message from daily signal run data.

Reads:
  - signals/YYYY-MM-DD/signals.json  (today's events & BUY signals)
  - signals/position_summary.json    (positions with current prices, exits)

Usage:
    python3 scripts/format_line_message.py --date 2026-02-11
"""

import argparse
import json
from pathlib import Path

DASHBOARD_URL = "https://contrarian-alpha.gpu5090.whaleforce.dev/dashboard"
MAX_POSITIONS_SHOWN = 20


def main():
    parser = argparse.ArgumentParser(description="Format LINE notification message")
    parser.add_argument("--date", required=True, help="Signal date (YYYY-MM-DD)")
    parser.add_argument("--base-dir", default=None,
                        help="Project base directory (default: auto-detect)")
    args = parser.parse_args()

    base = Path(args.base_dir) if args.base_dir else Path(__file__).resolve().parents[1]

    # ── Read today's signals ──────────────────────────────────────
    signal_path = base / "signals" / args.date / "signals.json"
    events = 0
    trades = 0
    buy_signals = []
    if signal_path.exists():
        try:
            data = json.load(open(signal_path))
            events = data.get("events", 0)
            trades = data.get("trades", 0)
            for s in data.get("signals", []):
                if s.get("action") == "BUY":
                    buy_signals.append({
                        "symbol": s["symbol"],
                        "prob": s["ml_prob"],
                        "sector": s.get("sector", ""),
                        "drop": s.get("drop_1d", 0),
                    })
        except (json.JSONDecodeError, KeyError):
            pass

    # ── Read position summary ─────────────────────────────────────
    summary_path = base / "signals" / "position_summary.json"
    positions = []
    exits = []
    open_count = 0
    closed_count = 0
    if summary_path.exists():
        try:
            summary = json.load(open(summary_path))
            positions = summary.get("positions", [])
            exits = summary.get("exits", [])
            open_count = summary.get("open_count", len(positions))
            closed_count = summary.get("closed_count", 0)
        except (json.JSONDecodeError, KeyError):
            pass

    # ── Build message ─────────────────────────────────────────────
    lines = []
    lines.append("📊 Contrarian Alpha Daily")
    lines.append(f"📅 {args.date}")
    lines.append("")
    lines.append(f"Events: {events} | Trades: {trades}")

    # BUY signals
    if buy_signals:
        lines.append("")
        lines.append("🟢 NEW BUY:")
        for s in buy_signals:
            sector_str = f" {s['sector']}" if s['sector'] else ""
            lines.append(f"  {s['symbol']} (prob={s['prob']:.3f}){sector_str}")
    else:
        lines.append("")
        lines.append("No new trades today.")

    # EXIT signals
    if exits:
        lines.append("")
        lines.append("🔴 EXIT:")
        for ex in exits:
            reason_map = {"take_profit": "TP", "stop_loss": "SL", "max_hold": "MH"}
            tag = reason_map.get(ex.get("exit_reason", ""), "??")
            sym = ex.get("symbol", "?")
            ret = ex.get("return_pct", 0)
            days = ex.get("hold_days_approx", "?")
            lines.append(f"  [{tag}] {sym} {ret:+.1f}% ({days}d)")

    # Position summary
    if positions:
        returns = [p["return_pct"] for p in positions]
        avg_ret = sum(returns) / len(returns) if returns else 0
        winners = sum(1 for r in returns if r > 0)
        losers = len(returns) - winners

        lines.append("")
        lines.append(f"📈 Positions: {len(positions)} "
                     f"(W:{winners} L:{losers} Avg:{avg_ret:+.1f}%)")

        # Highlights
        near_tp = [p for p in positions if p["return_pct"] >= 8.0]
        near_sl = [p for p in positions if p["return_pct"] <= -8.0]

        if near_tp:
            lines.append("🎯 Near TP:")
            for p in near_tp:
                lines.append(f"  {p['symbol']} {p['return_pct']:+.1f}%")

        if near_sl:
            lines.append("⚠️ Near SL:")
            for p in near_sl:
                lines.append(f"  {p['symbol']} {p['return_pct']:+.1f}%")

        # Full position list (sorted by return, descending)
        lines.append("")
        shown = positions[:MAX_POSITIONS_SHOWN]
        for p in shown:
            ret = p["return_pct"]
            indicator = "🟢" if ret > 0 else "🔴" if ret < 0 else "⚪"
            lines.append(f"{indicator} {p['symbol']:6s} {ret:+5.1f}% "
                         f"(${p['current_price']:,.0f})")
        if len(positions) > MAX_POSITIONS_SHOWN:
            lines.append(f"  ... +{len(positions) - MAX_POSITIONS_SHOWN} more")

    # Closed trades summary
    if closed_count > 0:
        lines.append("")
        lines.append(f"Closed trades: {closed_count}")

    # Dashboard link
    lines.append("")
    lines.append(f"🔗 {DASHBOARD_URL}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
