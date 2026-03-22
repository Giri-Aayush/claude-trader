"""
Tests for CryptoIntelligence — funding rate and open interest filters.
All DB calls are mocked so no Postgres needed.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from app.strategies.base import CandidateSignal
from app.services import crypto_intelligence


def _make_signal(direction: str = "LONG", confidence: float = 70.0) -> CandidateSignal:
    return CandidateSignal(
        strategy_name="liquidity_sweep",
        symbol="BTCUSDT",
        timeframe="M15",
        direction=direction,
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit=52000.0,
        confidence_score=confidence,
        reasoning="test signal",
        bar_index=100,
    )


class TestFundingRateFilter:
    @pytest.mark.asyncio
    async def test_high_positive_funding_blocks_long(self):
        """Funding rate > +0.1% → block LONG signals."""
        signal = _make_signal("LONG")
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0015)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=None)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is None

    @pytest.mark.asyncio
    async def test_high_positive_funding_allows_short(self):
        """Funding rate > +0.1% → SHORT signals are still allowed."""
        signal = _make_signal("SHORT")
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0015)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=None)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None

    @pytest.mark.asyncio
    async def test_high_negative_funding_blocks_short(self):
        """Funding rate < -0.1% → block SHORT signals."""
        signal = _make_signal("SHORT")
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=-0.0015)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=None)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is None

    @pytest.mark.asyncio
    async def test_high_negative_funding_allows_long(self):
        signal = _make_signal("LONG")
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=-0.0015)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=None)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None

    @pytest.mark.asyncio
    async def test_neutral_funding_passes_both_directions(self):
        for direction in ("LONG", "SHORT"):
            signal = _make_signal(direction)
            with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0002)):
                with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=None)):
                    result = await crypto_intelligence.filter_signal(signal)
            assert result is not None

    @pytest.mark.asyncio
    async def test_none_funding_passes_through(self):
        """If we can't fetch funding rate, don't block the signal."""
        signal = _make_signal("LONG")
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=None)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=None)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None

    @pytest.mark.asyncio
    async def test_funding_exactly_at_threshold_passes(self):
        """Exactly at threshold (0.001) should NOT block."""
        signal = _make_signal("LONG")
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.001)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=None)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None  # > not >=, so 0.001 passes


class TestOpenInterestFilter:
    @pytest.mark.asyncio
    async def test_oi_spike_boosts_confidence(self):
        """OI spiking >5% should boost confidence score by +5."""
        signal = _make_signal("LONG", confidence=70.0)
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=0.06)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None
        assert result.confidence_score == pytest.approx(75.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_oi_drop_reduces_confidence(self):
        """OI dropping >5% should reduce confidence by -10."""
        signal = _make_signal("LONG", confidence=70.0)
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=-0.06)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None
        assert result.confidence_score == pytest.approx(60.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_confidence_never_exceeds_100(self):
        signal = _make_signal("LONG", confidence=98.0)
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=0.10)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None
        assert result.confidence_score <= 100.0

    @pytest.mark.asyncio
    async def test_confidence_never_below_zero(self):
        signal = _make_signal("LONG", confidence=5.0)
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=-0.20)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None
        assert result.confidence_score >= 0.0

    @pytest.mark.asyncio
    async def test_small_oi_change_has_no_effect(self):
        signal = _make_signal("LONG", confidence=70.0)
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=0.02)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None
        assert result.confidence_score == pytest.approx(70.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_oi_reasoning_updated_on_spike(self):
        signal = _make_signal("LONG", confidence=70.0)
        with patch.object(crypto_intelligence, "get_latest_funding_rate", new=AsyncMock(return_value=0.0)):
            with patch.object(crypto_intelligence, "get_oi_change_pct", new=AsyncMock(return_value=0.08)):
                result = await crypto_intelligence.filter_signal(signal)
        assert result is not None
        assert "OI" in result.reasoning
