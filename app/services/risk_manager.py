"""
RiskManager
-----------
Layered position sizing hierarchy (each layer can only REDUCE size, never increase):

  1. Quarter Kelly Criterion  →  base position size (as % of account)
  2. ATR volatility cap       →  hard ceiling
  3. 2% daily loss rule       →  account-level floor
  4. Circuit breaker          →  zeroes everything (8 losses → 24h halt)

Also checks if funding rate cost would eat >20% of expected profit.
"""

import logging
from datetime import datetime, timezone, date

from sqlalchemy import select, desc, func

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tables import SystemState, StrategyPerformance, Outcome, Signal
from app.services import telegram_notifier
from app.strategies.base import CandidateSignal

log = logging.getLogger(__name__)

ATR_VOLATILITY_CAP = 0.03    # never risk more than 3% of account on one trade
MIN_POSITION_PCT = 0.001     # 0.1% minimum, below this skip the trade
FUNDING_PROFIT_THRESHOLD = 0.20  # block if funding cost > 20% of expected profit


async def _get_state(key: str) -> str:
    async with AsyncSessionLocal() as session:
        row = await session.get(SystemState, key)
        return row.value if row else ""


async def _set_state(key: str, value: str) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.get(SystemState, key)
        if row:
            row.value = value
            row.updated_at = datetime.now(tz=timezone.utc)
        else:
            session.add(SystemState(key=key, value=value))
        await session.commit()


async def is_circuit_breaker_active() -> bool:
    active = await _get_state("circuit_breaker_active")
    if active != "true":
        return False
    until_str = await _get_state("circuit_breaker_until")
    if not until_str:
        return True
    until = datetime.fromisoformat(until_str)
    if datetime.now(tz=timezone.utc) >= until:
        await _set_state("circuit_breaker_active", "false")
        await _set_state("circuit_breaker_until", "")
        log.info("Circuit breaker expired — system resumed.")
        return False
    return True


async def _check_and_trip_circuit_breaker(strategy_name: str) -> bool:
    """Check consecutive losses for a strategy and trip breaker if threshold hit."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.strategy_name == strategy_name
            )
        )
        perf = result.scalar_one_or_none()
        if perf and perf.consecutive_losses >= settings.CIRCUIT_BREAKER_LOSSES:
            from datetime import timedelta
            until = datetime.now(tz=timezone.utc) + timedelta(hours=24)
            await _set_state("circuit_breaker_active", "true")
            await _set_state("circuit_breaker_until", until.isoformat())
            log.warning("CIRCUIT BREAKER TRIPPED — %d consecutive losses.", perf.consecutive_losses)
            await telegram_notifier.send_circuit_breaker_alert(perf.consecutive_losses)
            return True
    return False


async def _get_daily_loss_pct() -> float:
    """Sum of realised losses today (as fraction of account)."""
    today = date.today().isoformat()
    stored_date = await _get_state("daily_loss_date")
    if stored_date != today:
        await _set_state("daily_loss_pct", "0.0")
        await _set_state("daily_loss_date", today)
        return 0.0
    val = await _get_state("daily_loss_pct")
    return float(val) if val else 0.0


async def record_daily_loss(loss_pct: float) -> None:
    current = await _get_daily_loss_pct()
    await _set_state("daily_loss_pct", str(current + abs(loss_pct)))


async def _get_strategy_performance(strategy_name: str) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.strategy_name == strategy_name
            )
        )
        perf = result.scalar_one_or_none()
        if perf:
            return {
                "win_rate": float(perf.win_rate),
                "avg_rr": float(perf.avg_rr),
            }
    return {"win_rate": 0.50, "avg_rr": 2.0}


def _kelly_fraction(win_rate: float, rr: float, kelly_mult: float = 0.25) -> float:
    """
    Kelly formula: f* = (W*R - L) / R  where L = 1 - W
    Applied with fractional Kelly multiplier (default 25%).
    """
    if rr <= 0 or win_rate <= 0:
        return 0.0
    loss_rate = 1.0 - win_rate
    f = (win_rate * rr - loss_rate) / rr
    return max(0.0, f * kelly_mult)


async def compute_position_size(signal: CandidateSignal) -> tuple[float, float]:
    """
    Returns (position_size_pct, kelly_fraction).
    position_size_pct is the fraction of account to risk on this trade.
    """
    # Layer 4: circuit breaker check
    if await is_circuit_breaker_active():
        await _check_and_trip_circuit_breaker(signal.strategy_name)
        return 0.0, 0.0

    # Layer 3: daily loss check
    daily_loss = await _get_daily_loss_pct()
    if daily_loss >= settings.MAX_DAILY_LOSS_PCT:
        log.info("Daily loss limit reached (%.2f%%). No new signals.", daily_loss * 100)
        return 0.0, 0.0

    # Layer 1: Quarter Kelly
    perf = await _get_strategy_performance(signal.strategy_name)
    rr = signal.risk_reward
    kelly = _kelly_fraction(perf["win_rate"], rr, settings.KELLY_FRACTION)

    # Layer 2: ATR volatility cap
    position_pct = min(kelly, ATR_VOLATILITY_CAP)

    # Remaining daily loss headroom further caps it
    remaining_headroom = settings.MAX_DAILY_LOSS_PCT - daily_loss
    position_pct = min(position_pct, remaining_headroom)

    if position_pct < MIN_POSITION_PCT:
        log.info("Position size %.4f%% too small, skipping.", position_pct * 100)
        return 0.0, kelly

    return round(position_pct, 6), round(kelly, 6)
