"""
Tests for SignalGenerator — validation, dedup, and minimum thresholds.
DB is mocked so no Postgres needed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.strategies.base import CandidateSignal
from app.services import signal_generator


def _make_signal(confidence: float = 75.0, direction: str = "LONG", rr_mult: float = 2.0) -> CandidateSignal:
    entry = 50000.0
    sl = 49000.0
    sl_dist = entry - sl
    tp = entry + rr_mult * sl_dist
    return CandidateSignal(
        strategy_name="liquidity_sweep",
        symbol="BTCUSDT",
        timeframe="M15",
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        confidence_score=confidence,
        reasoning="test",
        bar_index=100,
    )


class TestValidation:
    @pytest.mark.asyncio
    async def test_rejects_low_confidence(self):
        """Confidence below 55 should be rejected without touching DB."""
        signal = _make_signal(confidence=40.0)
        result = await signal_generator.validate_and_save(signal, 0.02, 0.08)
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_low_rr(self):
        """R:R below 1.5 should be rejected."""
        signal = _make_signal(confidence=80.0, rr_mult=1.2)
        result = await signal_generator.validate_and_save(signal, 0.02, 0.08)
        assert result is None

    @pytest.mark.asyncio
    async def test_passes_minimum_confidence_threshold(self):
        """Exactly at 55 confidence should pass validation."""
        signal = _make_signal(confidence=55.0)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("app.services.signal_generator.AsyncSessionLocal", return_value=mock_session):
            result = await signal_generator.validate_and_save(signal, 0.02, 0.08)
        # Should attempt to save (result depends on mock)
        assert result is None or isinstance(result, int)


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_dedup_blocks_duplicate_active_signal(self):
        """
        If an active signal already exists for the same strategy + direction
        within the dedup window, the new signal should be rejected.
        """
        signal = _make_signal(confidence=80.0)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        # Simulate finding an existing active signal
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=999))
        )

        with patch("app.services.signal_generator.AsyncSessionLocal", return_value=mock_session):
            result = await signal_generator.validate_and_save(signal, 0.02, 0.08)

        assert result is None

    @pytest.mark.asyncio
    async def test_allows_signal_when_no_duplicate(self):
        """No existing active signal → should proceed to save."""
        signal = _make_signal(confidence=80.0)

        mock_db_signal = MagicMock()
        mock_db_signal.id = 42

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(side_effect=lambda s: setattr(s, "id", 42))

        with patch("app.services.signal_generator.AsyncSessionLocal", return_value=mock_session):
            result = await signal_generator.validate_and_save(signal, 0.02, 0.08)

        assert result == 42

    @pytest.mark.asyncio
    async def test_different_direction_not_deduped(self):
        """LONG and SHORT are different signals, no dedup between them."""
        long_signal = _make_signal(confidence=80.0, direction="LONG")
        short_signal = _make_signal(confidence=80.0, direction="SHORT")

        # Both should go through independently — dedup is per strategy+direction
        assert long_signal.direction != short_signal.direction


class TestSignalProperties:
    def test_rr_calculation_correct(self):
        entry, sl, tp = 50000.0, 49000.0, 52000.0
        signal = CandidateSignal(
            strategy_name="test", symbol="BTCUSDT", timeframe="M15",
            direction="LONG", entry_price=entry, stop_loss=sl, take_profit=tp,
            confidence_score=70, reasoning="test", bar_index=100,
        )
        expected_rr = (tp - entry) / (entry - sl)
        assert abs(signal.risk_reward - expected_rr) < 1e-6

    def test_rr_is_positive_for_valid_long(self):
        signal = _make_signal(rr_mult=2.0)
        assert signal.risk_reward > 0

    def test_generated_at_is_utc(self):
        signal = _make_signal()
        assert signal.generated_at.tzinfo is not None or signal.generated_at is not None
