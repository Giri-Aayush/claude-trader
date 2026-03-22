"""
Tests for the Trend Continuation (EMA Pullback) strategy.
"""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timezone, timedelta

from app.strategies.trend_continuation import TrendContinuationStrategy
from app.strategies.base import CandidateSignal
from tests.conftest import make_candles, make_candle_set


strategy = TrendContinuationStrategy()


class TestTrendContinuationBasic:
    def test_returns_none_on_empty_data(self):
        assert strategy.generate({}) is None

    def test_returns_none_missing_timeframe(self):
        # Missing H4
        partial = {"M15": make_candles(), "H1": make_candles()}
        assert strategy.generate(partial) is None

    def test_returns_none_with_too_few_bars(self):
        short = {
            "M15": make_candles(n=30),
            "H1": make_candles(n=30),
            "H4": make_candles(n=30),
        }
        assert strategy.generate(short) is None

    def test_output_type_on_valid_input(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        assert result is None or isinstance(result, CandidateSignal)

    def test_strategy_name(self):
        assert strategy.name == "trend_continuation"


class TestTrendContinuationSignalProperties:
    def test_long_signal_direction_in_uptrend(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            # In an uptrend, only LONG signals should fire
            assert result.direction == "LONG"

    def test_short_signal_direction_in_downtrend(self):
        candles = make_candle_set("down")
        result = strategy.generate(candles)
        if result is not None:
            assert result.direction == "SHORT"

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

    def test_short_tp_below_entry(self):
        candles = make_candle_set("down")
        result = strategy.generate(candles)
        if result is not None and result.direction == "SHORT":
            assert result.take_profit < result.entry_price

    def test_minimum_rr(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.risk_reward >= 1.8

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

    def test_prices_positive(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert result.entry_price > 0
            assert result.stop_loss > 0
            assert result.take_profit > 0

    def test_reasoning_mentions_ema(self):
        candles = make_candle_set("up")
        result = strategy.generate(candles)
        if result is not None:
            assert "EMA" in result.reasoning or "ema" in result.reasoning.lower()
