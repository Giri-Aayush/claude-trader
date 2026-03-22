"""
Shared fixtures for the full test suite.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta


def make_candles(
    n: int = 250,
    trend: str = "up",
    base_price: float = 50000.0,
    volatility: float = 0.005,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate synthetic OHLCV candle data.

    trend: "up" | "down" | "flat"
    volatility: std dev of per-bar % change
    """
    rng = np.random.default_rng(seed)
    drift = {"up": 0.001, "down": -0.001, "flat": 0.0}[trend]

    prices = [base_price]
    for _ in range(n - 1):
        change = drift + rng.normal(0, volatility)
        prices.append(max(prices[-1] * (1 + change), 1.0))

    rows = []
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i, p in enumerate(prices):
        spread = p * volatility
        o = p
        h = p + abs(rng.normal(0, spread))
        l = p - abs(rng.normal(0, spread))
        c = p + rng.normal(0, spread * 0.5)
        c = float(np.clip(c, l, h))
        rows.append({
            "open_time": start + timedelta(minutes=15 * i),
            "open":  round(o, 2),
            "high":  round(h, 2),
            "low":   round(l, 2),
            "close": round(c, 2),
            "volume": round(float(rng.uniform(100, 1000)), 2),
        })

    return pd.DataFrame(rows)


def make_candle_set(trend: str = "up", n: int = 250) -> dict[str, pd.DataFrame]:
    """Return all four timeframes with the same trend."""
    return {
        "M15": make_candles(n=n, trend=trend, seed=1),
        "H1":  make_candles(n=n, trend=trend, seed=2),
        "H4":  make_candles(n=n, trend=trend, seed=3),
        "D1":  make_candles(n=n, trend=trend, seed=4),
    }


@pytest.fixture
def candles_up():
    return make_candle_set("up")


@pytest.fixture
def candles_down():
    return make_candle_set("down")


@pytest.fixture
def candles_flat():
    return make_candle_set("flat")
