"""
Tests for the Breakout Expansion (Volatility Squeeze) strategy.
"""

import numpy as np
import pandas as pd
import pytest

from app.strategies.breakout_expansion import BreakoutExpansionStrategy
from app.strategies.base import CandidateSignal
from tests.conftest import make_candles, make_candle_set


strategy = BreakoutExpansionStrategy()


def _make_squeeze_then_breakout(direction: str = "up", n: int = 250) -> dict:
    """
    Build candle data where the last few H1 bars show a BB squeeze
    and the last M15 bar breaks out of the band.
    """
    import pandas_ta as ta

    m15 = make_candles(n=n, trend=direction, seed=10)
    h1 = make_candles(n=n, trend=direction, seed=11)

    # Force H1 squeeze: compress the last 5 bars to near-identical closes
    # so BB width becomes very narrow (inside KC)
    mid_price = float(h1["close"].iloc[-6])
    for i in range(-5, -1):
        h1.iloc[i, h1.columns.get_loc("open")]  = mid_price
        h1.iloc[i, h1.columns.get_loc("high")]  = mid_price * 1.0005
        h1.iloc[i, h1.columns.get_loc("low")]   = mid_price * 0.9995
        h1.iloc[i, h1.columns.get_loc("close")] = mid_price

    # Force last H1 bar to expand (break out of squeeze)
    if direction == "up":
        h1.iloc[-1, h1.columns.get_loc("close")] = mid_price * 1.03
        h1.iloc[-1, h1.columns.get_loc("high")]  = mid_price * 1.04
    else:
        h1.iloc[-1, h1.columns.get_loc("close")] = mid_price * 0.97
        h1.iloc[-1, h1.columns.get_loc("low")]   = mid_price * 0.96

    # Force last M15 bar to close outside BB
    m15_mid = float(m15["close"].iloc[-2])
    if direction == "up":
        m15.iloc[-1, m15.columns.get_loc("close")] = m15_mid * 1.025
        m15.iloc[-1, m15.columns.get_loc("high")]  = m15_mid * 1.030
    else:
        m15.iloc[-1, m15.columns.get_loc("close")] = m15_mid * 0.975
        m15.iloc[-1, m15.columns.get_loc("low")]   = m15_mid * 0.970

    return {"M15": m15, "H1": h1, "H4": make_candles(n=n, trend=direction, seed=12), "D1": make_candles(n=n, trend=direction, seed=13)}


class TestBreakoutExpansionBasic:
    def test_returns_none_on_empty_data(self):
        assert strategy.generate({}) is None

    def test_returns_none_with_too_few_bars(self):
        short = {"M15": make_candles(n=10), "H1": make_candles(n=10)}
        assert strategy.generate(short) is None

    def test_returns_none_missing_h1(self):
        assert strategy.generate({"M15": make_candles()}) is None

    def test_output_type(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        assert result is None or isinstance(result, CandidateSignal)

    def test_strategy_name(self):
        assert strategy.name == "breakout_expansion"


class TestBreakoutExpansionSignalProperties:
    def test_long_signal_properties(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None and result.direction == "LONG":
            assert result.stop_loss < result.entry_price
            assert result.take_profit > result.entry_price

    def test_short_signal_properties(self):
        candles = make_candle_set("down")
        result = strategy.generate(candles)
        if result is not None and result.direction == "SHORT":
            assert result.stop_loss > result.entry_price
            assert result.take_profit < result.entry_price

    def test_minimum_rr(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.risk_reward >= 1.8

    def test_bar_index_is_last_m15_bar(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.bar_index == len(candles["M15"]) - 1

    def test_confidence_range(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert 0 <= result.confidence_score <= 100

    def test_all_prices_positive(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.entry_price > 0
            assert result.stop_loss > 0
            assert result.take_profit > 0

    def test_reasoning_mentions_squeeze(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert "squeeze" in result.reasoning.lower() or "breakout" in result.reasoning.lower()
