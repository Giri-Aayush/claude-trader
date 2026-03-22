"""
Tests for the EMA Momentum strategy.
"""

import numpy as np
import pandas as pd
import pytest

from app.strategies.ema_momentum import EmaMomentumStrategy
from app.strategies.base import CandidateSignal
from tests.conftest import make_candles, make_candle_set


strategy = EmaMomentumStrategy()


def _inject_bullish_cross(candles: dict) -> dict:
    """
    Force a fresh EMA9 > EMA21 crossover on the last M15 bar by making the
    last two bars diverge: prev bar EMA9 just below EMA21, last bar EMA9 above.
    We do this by pushing price sharply up on the last bar.
    """
    m15 = candles["M15"].copy()
    last_close = float(m15["close"].iloc[-2])
    # Push last bar price way up to force EMA9 above EMA21
    m15.iloc[-1, m15.columns.get_loc("close")] = last_close * 1.015
    m15.iloc[-1, m15.columns.get_loc("high")]  = last_close * 1.020
    m15.iloc[-1, m15.columns.get_loc("open")]  = last_close * 1.005

    # Also push H4 to high ADX — use a strongly trending H4 set
    h4 = make_candles(n=250, trend="up", volatility=0.012, seed=99)

    return {**candles, "M15": m15, "H4": h4}


def _inject_bearish_cross(candles: dict) -> dict:
    m15 = candles["M15"].copy()
    last_close = float(m15["close"].iloc[-2])
    m15.iloc[-1, m15.columns.get_loc("close")] = last_close * 0.985
    m15.iloc[-1, m15.columns.get_loc("low")]   = last_close * 0.980
    m15.iloc[-1, m15.columns.get_loc("open")]  = last_close * 0.995

    h4 = make_candles(n=250, trend="down", volatility=0.012, seed=100)
    return {**candles, "M15": m15, "H4": h4}


class TestEmaMomentumBasic:
    def test_returns_none_on_empty(self):
        assert strategy.generate({}) is None

    def test_returns_none_with_too_few_bars(self):
        short = {"M15": make_candles(n=20), "H4": make_candles(n=20)}
        assert strategy.generate(short) is None

    def test_returns_none_missing_h4(self):
        assert strategy.generate({"M15": make_candles()}) is None

    def test_output_type(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        assert result is None or isinstance(result, CandidateSignal)

    def test_strategy_name(self):
        assert strategy.name == "ema_momentum"


class TestEmaMomentumSignalProperties:
    def test_long_sl_below_entry(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None and result.direction == "LONG":
            assert result.stop_loss < result.entry_price

    def test_long_tp_above_entry(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None and result.direction == "LONG":
            assert result.take_profit > result.entry_price

    def test_short_sl_above_entry(self):
        candles = make_candle_set("down")
        result = strategy.generate(candles)
        if result is not None and result.direction == "SHORT":
            assert result.stop_loss > result.entry_price

    def test_minimum_rr(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.risk_reward >= 2.0

    def test_bar_index_is_last_bar(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.bar_index == len(candles["M15"]) - 1

    def test_confidence_range(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert 0 <= result.confidence_score <= 100

    def test_reasoning_mentions_adx(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert "ADX" in result.reasoning

    def test_prices_positive(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.entry_price > 0
            assert result.stop_loss > 0
            assert result.take_profit > 0
