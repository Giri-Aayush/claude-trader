"""
Tests for SignalPipeline orchestrator.
Every external dependency is mocked — this tests the control flow logic only.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.services import signal_pipeline
from app.strategies.base import CandidateSignal


def _good_signal() -> CandidateSignal:
    return CandidateSignal(
        strategy_name="liquidity_sweep",
        symbol="BTCUSDT",
        timeframe="M15",
        direction="LONG",
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit=52000.0,
        confidence_score=80.0,
        reasoning="test",
        bar_index=100,
    )


class TestPipelineControlFlow:
    @pytest.mark.asyncio
    async def test_stops_immediately_on_active_circuit_breaker(self):
        """If circuit breaker is active, pipeline exits without running strategies."""
        with patch("app.services.signal_pipeline.risk_manager.is_circuit_breaker_active", new=AsyncMock(return_value=True)):
            with patch("app.services.signal_pipeline.strategy_selector.run", new=AsyncMock()) as mock_run:
                await signal_pipeline.run()
                mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_stops_when_no_signal_from_strategies(self):
        """No candidate signal → pipeline exits before crypto intelligence."""
        with patch("app.services.signal_pipeline.risk_manager.is_circuit_breaker_active", new=AsyncMock(return_value=False)):
            with patch("app.services.signal_pipeline.strategy_selector.run", new=AsyncMock(return_value=None)):
                with patch("app.services.signal_pipeline.crypto_intelligence.filter_signal", new=AsyncMock()) as mock_ci:
                    await signal_pipeline.run()
                    mock_ci.assert_not_called()

    @pytest.mark.asyncio
    async def test_stops_when_crypto_intelligence_blocks_signal(self):
        """Signal blocked by CryptoIntelligence → position sizing is skipped."""
        with patch("app.services.signal_pipeline.risk_manager.is_circuit_breaker_active", new=AsyncMock(return_value=False)):
            with patch("app.services.signal_pipeline.strategy_selector.run", new=AsyncMock(return_value=_good_signal())):
                with patch("app.services.signal_pipeline.crypto_intelligence.filter_signal", new=AsyncMock(return_value=None)):
                    with patch("app.services.signal_pipeline.risk_manager.compute_position_size", new=AsyncMock()) as mock_rm:
                        await signal_pipeline.run()
                        mock_rm.assert_not_called()

    @pytest.mark.asyncio
    async def test_stops_when_position_size_is_zero(self):
        """Position size of 0 → signal generator is skipped."""
        with patch("app.services.signal_pipeline.risk_manager.is_circuit_breaker_active", new=AsyncMock(return_value=False)):
            with patch("app.services.signal_pipeline.strategy_selector.run", new=AsyncMock(return_value=_good_signal())):
                with patch("app.services.signal_pipeline.crypto_intelligence.filter_signal", new=AsyncMock(return_value=_good_signal())):
                    with patch("app.services.signal_pipeline.risk_manager.compute_position_size", new=AsyncMock(return_value=(0.0, 0.0))):
                        with patch("app.services.signal_pipeline.signal_generator.validate_and_save", new=AsyncMock()) as mock_sg:
                            await signal_pipeline.run()
                            mock_sg.assert_not_called()

    @pytest.mark.asyncio
    async def test_telegram_not_sent_when_signal_rejected_by_generator(self):
        """Signal rejected by dedup/validation → no Telegram message."""
        with patch("app.services.signal_pipeline.risk_manager.is_circuit_breaker_active", new=AsyncMock(return_value=False)):
            with patch("app.services.signal_pipeline.strategy_selector.run", new=AsyncMock(return_value=_good_signal())):
                with patch("app.services.signal_pipeline.crypto_intelligence.filter_signal", new=AsyncMock(return_value=_good_signal())):
                    with patch("app.services.signal_pipeline.risk_manager.compute_position_size", new=AsyncMock(return_value=(0.02, 0.08))):
                        with patch("app.services.signal_pipeline.signal_generator.validate_and_save", new=AsyncMock(return_value=None)):
                            with patch("app.services.signal_pipeline.telegram_notifier.send_signal", new=AsyncMock()) as mock_tg:
                                await signal_pipeline.run()
                                mock_tg.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_happy_path_sends_telegram(self):
        """Everything passes → Telegram signal is sent."""
        with patch("app.services.signal_pipeline.risk_manager.is_circuit_breaker_active", new=AsyncMock(return_value=False)):
            with patch("app.services.signal_pipeline.strategy_selector.run", new=AsyncMock(return_value=_good_signal())):
                with patch("app.services.signal_pipeline.crypto_intelligence.filter_signal", new=AsyncMock(return_value=_good_signal())):
                    with patch("app.services.signal_pipeline.risk_manager.compute_position_size", new=AsyncMock(return_value=(0.02, 0.08))):
                        with patch("app.services.signal_pipeline.signal_generator.validate_and_save", new=AsyncMock(return_value=42)):
                            with patch("app.services.signal_pipeline.telegram_notifier.send_signal", new=AsyncMock()) as mock_tg:
                                await signal_pipeline.run()
                                mock_tg.assert_called_once()

    @pytest.mark.asyncio
    async def test_telegram_called_with_correct_direction(self):
        """Telegram should receive the signal's direction."""
        signal = _good_signal()
        with patch("app.services.signal_pipeline.risk_manager.is_circuit_breaker_active", new=AsyncMock(return_value=False)):
            with patch("app.services.signal_pipeline.strategy_selector.run", new=AsyncMock(return_value=signal)):
                with patch("app.services.signal_pipeline.crypto_intelligence.filter_signal", new=AsyncMock(return_value=signal)):
                    with patch("app.services.signal_pipeline.risk_manager.compute_position_size", new=AsyncMock(return_value=(0.02, 0.08))):
                        with patch("app.services.signal_pipeline.signal_generator.validate_and_save", new=AsyncMock(return_value=1)):
                            with patch("app.services.signal_pipeline.telegram_notifier.send_signal", new=AsyncMock()) as mock_tg:
                                await signal_pipeline.run()
                                call_kwargs = mock_tg.call_args.kwargs
                                assert call_kwargs["direction"] == "LONG"
