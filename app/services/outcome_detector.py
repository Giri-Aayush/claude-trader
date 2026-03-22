"""
OutcomeDetector
---------------
Polls every 90 seconds for active signals and checks whether their
stop-loss or take-profit has been hit using the latest price from Binance.
"""

import logging
from datetime import datetime, timezone

import ccxt.async_support as ccxt
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tables import Signal, Outcome, StrategyPerformance
from app.services import risk_manager

log = logging.getLogger(__name__)


async def _get_current_price() -> float:
    exchange = ccxt.bybit({"options": {"defaultType": "linear"}})
    try:
        ticker = await exchange.fetch_ticker("BTC/USDT:USDT")
        return float(ticker["last"])
    finally:
        await exchange.close()


async def _resolve_signal(signal: Signal, exit_price: float, result: str) -> None:
    now = datetime.now(tz=timezone.utc)
    duration_min = int((now - signal.generated_at.replace(tzinfo=timezone.utc)).total_seconds() / 60)

    entry = float(signal.entry_price)
    if signal.direction == "LONG":
        pnl_pct = (exit_price - entry) / entry
    else:
        pnl_pct = (entry - exit_price) / entry

    async with AsyncSessionLocal() as session:
        # Save outcome
        outcome = Outcome(
            signal_id=signal.id,
            result=result,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            duration_minutes=duration_min,
            resolved_at=now,
        )
        session.add(outcome)

        # Update signal status
        db_signal = await session.get(Signal, signal.id)
        if db_signal:
            db_signal.status = result  # "WIN" or "LOSS"

        # Update strategy performance
        perf_result = await session.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.strategy_name == signal.strategy_name
            )
        )
        perf = perf_result.scalar_one_or_none()
        if perf:
            perf.total_trades = (perf.total_trades or 0) + 1
            if result == "WIN":
                perf.consecutive_losses = 0
            else:
                perf.consecutive_losses = (perf.consecutive_losses or 0) + 1
                await risk_manager.record_daily_loss(abs(pnl_pct) * float(signal.position_size_pct or 0))

            # Rolling win rate (simple exponential update)
            alpha = 0.1
            win_val = 1.0 if result == "WIN" else 0.0
            current_wr = float(perf.win_rate or 0.5)
            perf.win_rate = round(alpha * win_val + (1 - alpha) * current_wr, 4)
            perf.last_updated = now

        await session.commit()

    # Trip circuit breaker if consecutive losses threshold reached
    if result == "LOSS" and perf:
        await risk_manager._check_and_trip_circuit_breaker(signal.strategy_name)

    log.info("Signal %d resolved: %s @ %.2f (PnL: %.2f%%)", signal.id, result, exit_price, pnl_pct * 100)


async def _expire_stale_signals() -> None:
    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.status == "ACTIVE",
                Signal.expires_at <= now,
            )
        )
        stale = result.scalars().all()
        for s in stale:
            s.status = "EXPIRED"
            log.info("Signal %d expired.", s.id)
        await session.commit()


async def check_outcomes() -> None:
    """Main poll function — called every 90 seconds by APScheduler."""
    await _expire_stale_signals()

    try:
        current_price = await _get_current_price()
    except Exception as e:
        log.error("Failed to fetch current price: %s", e)
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Signal).where(Signal.status == "ACTIVE")
        )
        active_signals = result.scalars().all()

    for signal in active_signals:
        sl = float(signal.stop_loss)
        tp = float(signal.take_profit)

        if signal.direction == "LONG":
            if current_price <= sl:
                await _resolve_signal(signal, sl, "LOSS")
            elif current_price >= tp:
                await _resolve_signal(signal, tp, "WIN")
        elif signal.direction == "SHORT":
            if current_price >= sl:
                await _resolve_signal(signal, sl, "LOSS")
            elif current_price <= tp:
                await _resolve_signal(signal, tp, "WIN")
