"""
Tests for TradeSimulator — the most critical component.
Every test here guards against the look-ahead bug that cost $11,500.
"""

import pandas as pd
import pytest

from app.services.trade_simulator import simulate_trade, SimResult


def _make_df(bars: list[tuple]) -> pd.DataFrame:
    """
    bars: list of (open, high, low, close) tuples.
    """
    return pd.DataFrame(bars, columns=["open", "high", "low", "close"])


class TestAntiLookahead:
    """The most important tests in the entire suite."""

    def test_entry_is_at_next_bar_open_not_signal_bar_close(self):
        """
        Signal at bar 0 (close=100). Bar 1 opens at 105.
        Entry MUST be 105, never 100.
        """
        df = _make_df([
            (100, 110, 90, 100),   # bar 0 — signal bar
            (105, 200, 104, 195),  # bar 1 — entry bar, TP hit
        ])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=80, take_profit=200)
        assert result is not None
        assert result.entry_price == 105.0, "Entry must be bar N+1 open, not bar N close"

    def test_returns_none_when_no_bars_after_signal(self):
        """Signal is on the very last bar — nothing left to enter."""
        df = _make_df([(100, 110, 90, 100)])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=80, take_profit=120)
        assert result is None

    def test_returns_none_when_bar_index_is_last(self):
        df = _make_df([
            (100, 110, 90, 100),
            (105, 115, 95, 108),
        ])
        result = simulate_trade(df, bar_index=1, direction="LONG", stop_loss=80, take_profit=200)
        assert result is None


class TestLongTrades:
    def test_long_win_tp_hit(self):
        df = _make_df([
            (100, 105, 98, 103),   # bar 0 — signal
            (104, 130, 103, 128),  # bar 1 — TP hit (TP=125)
        ])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=90, take_profit=125)
        assert result is not None
        assert result.result == "WIN"
        assert result.exit_price == 125
        assert result.pnl_pct > 0

    def test_long_loss_sl_hit(self):
        df = _make_df([
            (100, 105, 98, 103),   # bar 0 — signal
            (104, 106, 85, 87),    # bar 1 — SL hit (SL=90)
        ])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=90, take_profit=200)
        assert result is not None
        assert result.result == "LOSS"
        assert result.exit_price == 90
        assert result.pnl_pct < 0

    def test_long_sl_checked_before_tp_within_same_bar(self):
        """
        When SL and TP are both within the same bar's range, SL takes priority
        (conservative — worst case first).
        """
        df = _make_df([
            (100, 105, 98, 103),    # bar 0 — signal
            (104, 200, 80, 150),    # bar 1 — both SL=90 and TP=150 in range
        ])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=90, take_profit=150)
        assert result is not None
        assert result.result == "LOSS"  # SL first

    def test_long_pnl_calculation(self):
        df = _make_df([
            (100, 105, 98, 103),
            (110, 160, 109, 155),  # entry=110, TP=150 hit
        ])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=90, take_profit=150)
        assert result is not None
        assert result.result == "WIN"
        expected_pnl = (150 - 110) / 110
        assert abs(result.pnl_pct - expected_pnl) < 1e-6


class TestShortTrades:
    def test_short_win_tp_hit(self):
        df = _make_df([
            (100, 102, 95, 98),    # bar 0 — signal
            (97, 98, 70, 72),      # bar 1 — TP hit (TP=75)
        ])
        result = simulate_trade(df, bar_index=0, direction="SHORT", stop_loss=110, take_profit=75)
        assert result is not None
        assert result.result == "WIN"
        assert result.exit_price == 75
        assert result.pnl_pct > 0

    def test_short_loss_sl_hit(self):
        df = _make_df([
            (100, 102, 95, 98),     # bar 0 — signal
            (97, 115, 96, 113),     # bar 1 — SL hit (SL=110)
        ])
        result = simulate_trade(df, bar_index=0, direction="SHORT", stop_loss=110, take_profit=75)
        assert result is not None
        assert result.result == "LOSS"
        assert result.exit_price == 110
        assert result.pnl_pct < 0

    def test_short_pnl_calculation(self):
        df = _make_df([
            (100, 102, 95, 98),
            (96, 97, 60, 62),      # entry=96, TP=75 hit
        ])
        result = simulate_trade(df, bar_index=0, direction="SHORT", stop_loss=120, take_profit=75)
        assert result is not None
        assert result.result == "WIN"
        expected_pnl = (96 - 75) / 96
        assert abs(result.pnl_pct - expected_pnl) < 1e-6


class TestExpiredTrades:
    def test_trade_expires_after_max_bars(self):
        """When neither SL nor TP is hit, trade should expire."""
        # 5 bars all hovering between SL and TP
        bars = [(100, 105, 98, 102)] + [(102, 106, 99, 103)] * 5
        df = _make_df(bars)
        # SL=50, TP=200 — never hit
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=50, take_profit=200)
        # With only 5 future bars (well below MAX_BARS=200), it expires
        assert result is not None
        assert result.result in ("WIN", "LOSS")  # based on final close vs entry

    def test_expired_pnl_based_on_final_close(self):
        bars = [
            (100, 102, 98, 101),   # bar 0 signal
            (101, 103, 100, 102),  # bars 1-3: hover, never hit SL=50 or TP=200
            (102, 104, 101, 110),
            (110, 112, 108, 115),
        ]
        df = _make_df(bars)
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=50, take_profit=200)
        assert result is not None
        # entry=101 (bar 1 open), exit=115 (last close) — should be win
        assert result.pnl_pct > 0


class TestMultiBarResolution:
    def test_tp_hit_on_third_bar(self):
        df = _make_df([
            (100, 102, 98, 101),   # bar 0 — signal
            (101, 103, 100, 102),  # bar 1 — no hit
            (102, 103, 101, 102),  # bar 2 — no hit
            (102, 155, 101, 150),  # bar 3 — TP=140 hit
        ])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=90, take_profit=140)
        assert result is not None
        assert result.result == "WIN"
        assert result.duration_bars == 3

    def test_sl_hit_on_second_bar(self):
        df = _make_df([
            (100, 102, 98, 101),
            (101, 102, 100, 101),  # no hit
            (101, 102, 75, 80),    # SL=90 hit
        ])
        result = simulate_trade(df, bar_index=0, direction="LONG", stop_loss=90, take_profit=200)
        assert result is not None
        assert result.result == "LOSS"
        assert result.duration_bars == 2
