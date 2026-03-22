"""
TradeSimulator
--------------
Simulates trade outcomes on historical candle data.

CRITICAL anti-lookahead rule:
  - The signal is generated at bar_index N (the last closed bar).
  - Simulation starts at bar N+1 (entry = open of bar N+1).
  - We never use the close of bar N as the entry price.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd


MAX_BARS = 200  # max bars to hold a trade before expiring it


@dataclass
class SimResult:
    result: str         # "WIN", "LOSS", or "EXPIRED"
    entry_price: float
    exit_price: float
    pnl_pct: float      # positive = profit, negative = loss
    duration_bars: int


def simulate_trade(
    df: pd.DataFrame,
    bar_index: int,
    direction: str,
    stop_loss: float,
    take_profit: float,
) -> Optional[SimResult]:
    """
    Simulate a trade on df starting from bar_index + 1.

    df must have columns: open, high, low, close (all numeric).
    bar_index is the index of the signal bar in df.
    """
    entry_bar = bar_index + 1
    if entry_bar >= len(df):
        return None  # not enough future bars

    entry_price = float(df["open"].iloc[entry_bar])

    for i in range(entry_bar, min(entry_bar + MAX_BARS, len(df))):
        bar_high = float(df["high"].iloc[i])
        bar_low = float(df["low"].iloc[i])

        if direction == "LONG":
            # Check SL first (conservative — worst case within a bar)
            if bar_low <= stop_loss:
                exit_price = stop_loss
                pnl_pct = (exit_price - entry_price) / entry_price
                return SimResult("LOSS", entry_price, exit_price, pnl_pct, i - entry_bar + 1)
            if bar_high >= take_profit:
                exit_price = take_profit
                pnl_pct = (exit_price - entry_price) / entry_price
                return SimResult("WIN", entry_price, exit_price, pnl_pct, i - entry_bar + 1)

        elif direction == "SHORT":
            if bar_high >= stop_loss:
                exit_price = stop_loss
                pnl_pct = (entry_price - exit_price) / entry_price
                return SimResult("LOSS", entry_price, exit_price, pnl_pct, i - entry_bar + 1)
            if bar_low <= take_profit:
                exit_price = take_profit
                pnl_pct = (entry_price - exit_price) / entry_price
                return SimResult("WIN", entry_price, exit_price, pnl_pct, i - entry_bar + 1)

    # Trade expired without hitting SL or TP
    exit_price = float(df["close"].iloc[min(entry_bar + MAX_BARS - 1, len(df) - 1)])
    if direction == "LONG":
        pnl_pct = (exit_price - entry_price) / entry_price
    else:
        pnl_pct = (entry_price - exit_price) / entry_price
    result = "WIN" if pnl_pct > 0 else "LOSS"
    return SimResult(result, entry_price, exit_price, pnl_pct, MAX_BARS)
