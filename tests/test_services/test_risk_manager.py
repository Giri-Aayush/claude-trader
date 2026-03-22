"""
Tests for RiskManager — Kelly criterion, ATR cap, daily loss rule, circuit breaker.
We test the pure Kelly math directly without touching the database.
"""

import pytest

from app.services.risk_manager import _kelly_fraction


class TestKellyCriterion:
    def test_positive_kelly_with_good_strategy(self):
        """60% win rate + 2R should produce a positive Kelly fraction."""
        k = _kelly_fraction(win_rate=0.60, rr=2.0, kelly_mult=1.0)
        assert k > 0

    def test_zero_kelly_below_breakeven(self):
        """40% WR with 1R is a losing strategy — Kelly returns 0."""
        k = _kelly_fraction(win_rate=0.40, rr=1.0, kelly_mult=1.0)
        assert k == 0.0

    def test_quarter_kelly_is_25_percent_of_full(self):
        full = _kelly_fraction(win_rate=0.60, rr=2.0, kelly_mult=1.0)
        quarter = _kelly_fraction(win_rate=0.60, rr=2.0, kelly_mult=0.25)
        assert abs(quarter - full * 0.25) < 1e-9

    def test_kelly_never_negative(self):
        """Even for losing strategies, Kelly must be clipped to 0."""
        k = _kelly_fraction(win_rate=0.20, rr=0.5, kelly_mult=0.25)
        assert k >= 0.0

    def test_higher_rr_gives_higher_kelly(self):
        k_low = _kelly_fraction(win_rate=0.55, rr=1.5, kelly_mult=0.25)
        k_high = _kelly_fraction(win_rate=0.55, rr=3.0, kelly_mult=0.25)
        assert k_high > k_low

    def test_higher_win_rate_gives_higher_kelly(self):
        k_low = _kelly_fraction(win_rate=0.50, rr=2.0, kelly_mult=0.25)
        k_high = _kelly_fraction(win_rate=0.65, rr=2.0, kelly_mult=0.25)
        assert k_high > k_low

    def test_zero_rr_returns_zero(self):
        k = _kelly_fraction(win_rate=0.60, rr=0.0, kelly_mult=0.25)
        assert k == 0.0

    def test_zero_win_rate_returns_zero(self):
        k = _kelly_fraction(win_rate=0.0, rr=2.0, kelly_mult=0.25)
        assert k == 0.0

    def test_kelly_formula_manual_check(self):
        """
        Manual: WR=0.6, L=0.4, R=2
        f* = (0.6*2 - 0.4) / 2 = (1.2 - 0.4) / 2 = 0.4
        quarter = 0.4 * 0.25 = 0.1
        """
        k = _kelly_fraction(win_rate=0.60, rr=2.0, kelly_mult=0.25)
        assert abs(k - 0.1) < 1e-9

    def test_kelly_formula_another_example(self):
        """
        WR=0.55, L=0.45, R=1.5
        f* = (0.55*1.5 - 0.45) / 1.5 = (0.825 - 0.45) / 1.5 = 0.25
        quarter = 0.25 * 0.25 = 0.0625
        """
        k = _kelly_fraction(win_rate=0.55, rr=1.5, kelly_mult=0.25)
        assert abs(k - 0.0625) < 1e-9

    def test_atr_cap_implicit(self):
        """
        Even a very high Kelly shouldn't exceed ATR_VOLATILITY_CAP (3%).
        We test that the raw Kelly math can exceed 3% so we know the cap is needed.
        """
        # Very high WR + high RR → full Kelly > 3%
        k_full = _kelly_fraction(win_rate=0.80, rr=5.0, kelly_mult=1.0)
        assert k_full > 0.03  # proves the cap is meaningful
