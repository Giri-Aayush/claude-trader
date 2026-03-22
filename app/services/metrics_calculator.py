"""
MetricsCalculator
-----------------
Computes win rate, Sharpe ratio, max drawdown, and expectancy
from a list of pnl_pct values.
"""

import math
from typing import Sequence


SANITY_WIN_RATE_THRESHOLD = 0.70
SANITY_SHARPE_THRESHOLD = 3.0


def compute_metrics(pnl_list: Sequence[float]) -> dict:
    """
    pnl_list: sequence of per-trade P&L as decimals (e.g. 0.02 = +2%, -0.01 = -1%).
    Returns a dict with: win_rate, sharpe, max_drawdown, expectancy,
                         total_trades, is_suspicious.
    """
    if not pnl_list:
        return {
            "win_rate": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "expectancy": 0.0,
            "total_trades": 0,
            "is_suspicious": False,
        }

    n = len(pnl_list)
    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p <= 0]

    win_rate = len(wins) / n
    expectancy = sum(pnl_list) / n

    # Sharpe ratio (annualised assuming M15 bars, ~26,280 bars/year)
    mean_pnl = expectancy
    if n > 1:
        variance = sum((p - mean_pnl) ** 2 for p in pnl_list) / (n - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 1e-9
    else:
        std_pnl = 1e-9
    bars_per_year = 26_280
    sharpe = (mean_pnl / std_pnl) * math.sqrt(bars_per_year / max(n, 1))

    # Max drawdown (peak-to-trough on cumulative equity curve)
    equity = [1.0]
    for p in pnl_list:
        equity.append(equity[-1] * (1 + p))
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd

    # Sanity check — flag impossibly good results (likely a data leak)
    is_suspicious = win_rate > SANITY_WIN_RATE_THRESHOLD or sharpe > SANITY_SHARPE_THRESHOLD

    return {
        "win_rate": round(win_rate, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "expectancy": round(expectancy, 6),
        "total_trades": n,
        "is_suspicious": is_suspicious,
    }
