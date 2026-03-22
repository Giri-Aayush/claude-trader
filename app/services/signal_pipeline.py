"""
SignalPipeline (Orchestrator)
-----------------------------
Full signal lifecycle in one function. Called every 30 minutes.

Flow:
  StrategySelector → CryptoIntelligence → RiskManager → SignalGenerator → TelegramNotifier
"""

import logging

from app.services import (
    strategy_selector,
    crypto_intelligence,
    risk_manager,
    signal_generator,
    telegram_notifier,
)

log = logging.getLogger(__name__)


async def run() -> None:
    log.info("SignalPipeline: starting run.")

    # 1. Check circuit breaker before doing any work
    if await risk_manager.is_circuit_breaker_active():
        log.info("SignalPipeline: circuit breaker active, skipping.")
        return

    # 2. Run strategy selector — returns best candidate signal or None
    candidate = await strategy_selector.run()
    if candidate is None:
        log.info("SignalPipeline: no signal generated this run.")
        return

    log.info(
        "SignalPipeline: candidate signal — %s %s @ %.2f (conf=%.1f)",
        candidate.direction, candidate.strategy_name,
        candidate.entry_price, candidate.confidence_score,
    )

    # 3. CryptoIntelligence filter (funding rate + OI check)
    candidate = await crypto_intelligence.filter_signal(candidate)
    if candidate is None:
        log.info("SignalPipeline: signal blocked by CryptoIntelligence.")
        return

    # 4. RiskManager — compute position size
    position_pct, kelly = await risk_manager.compute_position_size(candidate)
    if position_pct == 0.0:
        log.info("SignalPipeline: position size zeroed by RiskManager, skipping.")
        return

    # 5. Validate and save signal
    signal_id = await signal_generator.validate_and_save(candidate, position_pct, kelly)
    if signal_id is None:
        log.info("SignalPipeline: signal rejected by SignalGenerator.")
        return

    # 6. Send Telegram alert
    await telegram_notifier.send_signal(
        direction=candidate.direction,
        strategy=candidate.strategy_name,
        entry=candidate.entry_price,
        sl=candidate.stop_loss,
        tp=candidate.take_profit,
        confidence=candidate.confidence_score,
        reasoning=candidate.reasoning,
        position_pct=position_pct,
    )

    log.info("SignalPipeline: signal %d dispatched successfully.", signal_id)
