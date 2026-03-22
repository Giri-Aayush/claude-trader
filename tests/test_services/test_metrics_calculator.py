"""
Tests for MetricsCalculator.
Includes the sanity-check logic that catches the look-ahead data leak.
"""

import math
import pytest

from app.services.metrics_calculator import compute_metrics


class TestEmptyAndEdgeCases:
    def test_empty_list_returns_zeros(self):
        result = compute_metrics([])
        assert result["win_rate"] == 0.0
        assert result["sharpe"] == 0.0
        assert result["max_drawdown"] == 0.0
        assert result["expectancy"] == 0.0
        assert result["total_trades"] == 0
        assert result["is_suspicious"] is False

    def test_single_winning_trade(self):
        result = compute_metrics([0.05])
        assert result["win_rate"] == 1.0
        assert result["total_trades"] == 1

    def test_single_losing_trade(self):
        result = compute_metrics([-0.02])
        assert result["win_rate"] == 0.0
        assert result["total_trades"] == 1


class TestWinRate:
    def test_all_wins(self):
        result = compute_metrics([0.02, 0.03, 0.01, 0.04])
        assert result["win_rate"] == 1.0

    def test_all_losses(self):
        result = compute_metrics([-0.02, -0.01, -0.03])
        assert result["win_rate"] == 0.0

    def test_50_percent_win_rate(self):
        result = compute_metrics([0.02, -0.01, 0.03, -0.02])
        assert result["win_rate"] == 0.5

    def test_win_rate_correct_count(self):
        pnls = [0.01, -0.01, 0.02, -0.02, 0.03]  # 3 wins, 2 losses
        result = compute_metrics(pnls)
        assert result["win_rate"] == pytest.approx(3 / 5)

    def test_win_rate_between_zero_and_one(self):
        pnls = [0.01 * i - 0.005 for i in range(20)]
        result = compute_metrics(pnls)
        assert 0.0 <= result["win_rate"] <= 1.0


class TestSharpeRatio:
    def test_positive_sharpe_for_profitable_strategy(self):
        # Consistently positive returns → positive Sharpe
        pnls = [0.02] * 50
        result = compute_metrics(pnls)
        assert result["sharpe"] > 0

    def test_negative_sharpe_for_losing_strategy(self):
        pnls = [-0.02] * 50
        result = compute_metrics(pnls)
        assert result["sharpe"] < 0

    def test_higher_sharpe_for_more_consistent_strategy(self):
        consistent = [0.02] * 100
        noisy = [0.02 + (0.1 if i % 2 == 0 else -0.06) for i in range(100)]
        r_consistent = compute_metrics(consistent)
        r_noisy = compute_metrics(noisy)
        assert r_consistent["sharpe"] > r_noisy["sharpe"]


class TestMaxDrawdown:
    def test_no_drawdown_on_all_wins(self):
        pnls = [0.01, 0.02, 0.01]
        result = compute_metrics(pnls)
        assert result["max_drawdown"] == pytest.approx(0.0, abs=1e-6)

    def test_drawdown_detected_on_losing_streak(self):
        # Win, then two losses, then recovery
        pnls = [0.1, -0.05, -0.05, 0.1]
        result = compute_metrics(pnls)
        assert result["max_drawdown"] > 0

    def test_drawdown_is_between_zero_and_one(self):
        pnls = [0.02, -0.05, 0.03, -0.04, 0.06]
        result = compute_metrics(pnls)
        assert 0.0 <= result["max_drawdown"] <= 1.0

    def test_max_drawdown_worst_case(self):
        # 50% loss then recovery — drawdown must be close to 0.5
        pnls = [-0.5, 1.0]
        result = compute_metrics(pnls)
        assert result["max_drawdown"] == pytest.approx(0.5, abs=0.01)


class TestSanityCheck:
    def test_flags_suspicious_on_high_win_rate(self):
        """Win rate > 70% in a real system almost always means a data leak."""
        pnls = [0.02] * 100 + [-0.01] * 10  # ~91% win rate
        result = compute_metrics(pnls)
        assert result["win_rate"] > 0.70
        assert result["is_suspicious"] is True

    def test_flags_suspicious_on_high_sharpe(self):
        """Sharpe > 3 is suspicious for a trading strategy."""
        # Very consistent +2% per trade → astronomically high Sharpe
        pnls = [0.02] * 200
        result = compute_metrics(pnls)
        assert result["sharpe"] > 3.0
        assert result["is_suspicious"] is True

    def test_not_suspicious_for_realistic_metrics(self):
        """
        Realistic strategy: ~58% WR with 1000 trades.
        Annualisation factor drops to sqrt(26280/1000)≈5.1, keeping Sharpe below 3.
        """
        import random
        random.seed(42)
        pnls = []
        for _ in range(1000):
            if random.random() < 0.58:
                pnls.append(random.uniform(-0.01, 0.06))   # wide win range
            else:
                pnls.append(random.uniform(-0.04, 0.005))  # wide loss range
        result = compute_metrics(pnls)
        # Win rate below 70% → not suspicious on that axis
        assert result["win_rate"] < 0.70
        assert result["is_suspicious"] is False

    def test_total_trades_count(self):
        pnls = [0.01, -0.02, 0.03]
        result = compute_metrics(pnls)
        assert result["total_trades"] == 3

    def test_expectancy_positive_for_profitable(self):
        pnls = [0.03, 0.03, -0.01, 0.03]
        result = compute_metrics(pnls)
        assert result["expectancy"] > 0

    def test_expectancy_negative_for_losing(self):
        pnls = [-0.02, -0.03, 0.01, -0.02]
        result = compute_metrics(pnls)
        assert result["expectancy"] < 0
