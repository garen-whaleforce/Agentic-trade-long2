"""
Backtest Report Parser.

Parses and formats backtest results from Whaleforce API.
"""

from typing import Dict, Any, Optional

from services.whaleforce_backtest_client import BacktestResult


class BacktestReportParser:
    """
    Parses backtest results into various formats.

    All metrics are from the API - no local calculations.
    """

    def __init__(self, result: BacktestResult):
        """
        Initialize the parser.

        Args:
            result: BacktestResult from API
        """
        self.result = result

    def to_summary(self) -> Dict[str, Any]:
        """
        Convert to summary dictionary.

        Returns:
            Summary of key metrics
        """
        perf = self.result.performance
        stats = self.result.trade_stats

        return {
            "backtest_id": self.result.backtest_id,
            "strategy_id": self.result.strategy_id,
            "status": self.result.status,
            "performance": {
                "cagr_pct": perf.cagr * 100,
                "sharpe_ratio": perf.sharpe_ratio,
                "sortino_ratio": perf.sortino_ratio,
                "win_rate_pct": perf.win_rate * 100,
                "max_drawdown_pct": perf.max_drawdown * 100,
                "profit_factor": perf.profit_factor,
            },
            "trade_stats": {
                "total_trades": stats.total_trades,
                "winning_trades": stats.winning_trades,
                "losing_trades": stats.losing_trades,
                "trades_per_year": stats.trades_per_year,
                "avg_holding_days": stats.avg_holding_days,
            },
        }

    def to_markdown(self) -> str:
        """
        Convert to markdown report.

        Returns:
            Markdown formatted report
        """
        perf = self.result.performance
        stats = self.result.trade_stats

        lines = []
        lines.append("# Backtest Report")
        lines.append("")
        lines.append(f"**Backtest ID:** {self.result.backtest_id}")
        lines.append(f"**Strategy:** {self.result.strategy_id}")
        lines.append(f"**Status:** {self.result.status}")
        lines.append("")

        lines.append("## Performance Metrics (from Whaleforce API)")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| CAGR | {perf.cagr * 100:.1f}% |")
        lines.append(f"| Sharpe Ratio | {perf.sharpe_ratio:.2f} |")
        lines.append(f"| Sortino Ratio | {perf.sortino_ratio:.2f} |")
        lines.append(f"| Win Rate | {perf.win_rate * 100:.1f}% |")
        lines.append(f"| Max Drawdown | {perf.max_drawdown * 100:.1f}% |")
        lines.append(f"| Profit Factor | {perf.profit_factor:.2f} |")
        lines.append(f"| Total Return | {perf.total_return * 100:.1f}% |")
        lines.append(f"| Volatility | {perf.annualized_volatility * 100:.1f}% |")
        lines.append("")

        lines.append("## Trade Statistics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Trades | {stats.total_trades} |")
        lines.append(f"| Winning Trades | {stats.winning_trades} |")
        lines.append(f"| Losing Trades | {stats.losing_trades} |")
        lines.append(f"| Trades/Year | {stats.trades_per_year:.0f} |")
        lines.append(f"| Avg Holding Days | {stats.avg_holding_days:.0f} |")
        lines.append(f"| Avg Win | {stats.avg_win * 100:.1f}% |")
        lines.append(f"| Avg Loss | {stats.avg_loss * 100:.1f}% |")
        lines.append("")

        lines.append("## Yearly Returns")
        lines.append("")
        lines.append("| Year | Return |")
        lines.append("|------|--------|")
        for year, ret in sorted(self.result.yearly_returns.items()):
            lines.append(f"| {year} | {ret * 100:.1f}% |")
        lines.append("")

        lines.append("---")
        lines.append("*All metrics sourced from Whaleforce Backtest API (SSOT)*")

        return "\n".join(lines)

    def check_targets(
        self,
        min_cagr: float = 0.35,
        min_sharpe: float = 2.0,
        min_win_rate: float = 0.75,
    ) -> Dict[str, bool]:
        """
        Check if results meet targets.

        Args:
            min_cagr: Minimum CAGR target
            min_sharpe: Minimum Sharpe target
            min_win_rate: Minimum win rate target

        Returns:
            Dictionary with pass/fail for each target
        """
        perf = self.result.performance

        return {
            "cagr_pass": perf.cagr >= min_cagr,
            "sharpe_pass": perf.sharpe_ratio >= min_sharpe,
            "win_rate_pass": perf.win_rate >= min_win_rate,
            "all_pass": (
                perf.cagr >= min_cagr
                and perf.sharpe_ratio >= min_sharpe
                and perf.win_rate >= min_win_rate
            ),
            "targets": {
                "cagr": {"target": min_cagr, "actual": perf.cagr},
                "sharpe": {"target": min_sharpe, "actual": perf.sharpe_ratio},
                "win_rate": {"target": min_win_rate, "actual": perf.win_rate},
            },
        }
