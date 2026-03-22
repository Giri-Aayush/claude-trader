"""
SignalGenerator
---------------
Validates and deduplicates candidate signals before writing to DB.

Dedup rule: if an active/pending signal already exists for the same
strategy + direction within the last 2 hours, discard the new one.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.tables import Signal
from app.strategies.base import CandidateSignal

log = logging.getLogger(__name__)

DEDUP_WINDOW_HOURS = 2
MIN_CONFIDENCE = 55.0


async def validate_and_save(
    signal: CandidateSignal,
    position_size_pct: float,
    kelly_fraction: float,
) -> Optional[int]:
    """
    Validate signal, check for duplicates, and persist to DB.
    Returns the new signal ID, or None if rejected.
    """

    # Minimum confidence threshold
    if signal.confidence_score < MIN_CONFIDENCE:
        log.info("Signal rejected: confidence %.1f < %.1f", signal.confidence_score, MIN_CONFIDENCE)
        return None

    # Minimum R:R
    if signal.risk_reward < 1.5:
        log.info("Signal rejected: R:R %.2f < 1.5", signal.risk_reward)
        return None

    window_start = datetime.now(tz=timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)

    async with AsyncSessionLocal() as session:
        # Deduplication check
        existing = await session.execute(
            select(Signal.id).where(
                Signal.strategy_name == signal.strategy_name,
                Signal.direction == signal.direction,
                Signal.status.in_(["PENDING", "ACTIVE"]),
                Signal.generated_at >= window_start,
            )
        )
        if existing.scalar_one_or_none() is not None:
            log.info(
                "Duplicate signal skipped: %s %s already active within %dh window.",
                signal.strategy_name, signal.direction, DEDUP_WINDOW_HOURS,
            )
            return None

        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=4)

        db_signal = Signal(
            strategy_name=signal.strategy_name,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            direction=signal.direction,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            confidence_score=signal.confidence_score,
            reasoning=signal.reasoning,
            position_size_pct=position_size_pct,
            kelly_fraction=kelly_fraction,
            bar_index=signal.bar_index,
            generated_at=signal.generated_at,
            expires_at=expires_at,
            status="ACTIVE",
        )
        session.add(db_signal)
        await session.commit()
        await session.refresh(db_signal)
        log.info("Signal saved: id=%d %s %s", db_signal.id, signal.direction, signal.strategy_name)
        return db_signal.id
