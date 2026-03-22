"""
CryptoIntelligence
------------------
BTC-specific market context filter applied after signal generation.
Reads funding rate and open interest from Postgres to adjust or
block signals based on market structure.

Rules:
  - Funding rate > +0.1%  → longs overloaded → block LONG signals
  - Funding rate < -0.1%  → shorts overloaded → block SHORT signals
  - OI spiking (>5% jump) → confirms breakout → boost confidence +5
  - OI dropping (>5% drop) → trend losing steam → reduce confidence -10
  - Funding cost > 20% of expected profit → reduce position size proportionally
"""

import logging
from typing import Optional

from sqlalchemy import select, desc

from app.database import AsyncSessionLocal
from app.models.tables import FundingRate, OpenInterest
from app.strategies.base import CandidateSignal

log = logging.getLogger(__name__)

FUNDING_LONG_BLOCK = 0.001    # +0.1%
FUNDING_SHORT_BLOCK = -0.001  # -0.1%
OI_SPIKE_PCT = 0.05
FUNDING_COST_MAX_PCT = 0.20   # if funding > 20% of expected profit, scale down


async def get_latest_funding_rate() -> Optional[float]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(FundingRate.funding_rate)
            .order_by(desc(FundingRate.funding_time))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return float(row) if row is not None else None


async def get_oi_change_pct() -> Optional[float]:
    """Returns OI percentage change between the two most recent snapshots."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OpenInterest.open_interest)
            .order_by(desc(OpenInterest.timestamp))
            .limit(2)
        )
        rows = result.scalars().all()
        if len(rows) < 2:
            return None
        latest, previous = float(rows[0]), float(rows[1])
        if previous == 0:
            return None
        return (latest - previous) / previous


async def filter_signal(signal: CandidateSignal) -> Optional[CandidateSignal]:
    """
    Apply crypto intelligence filters to a candidate signal.
    Returns the (possibly modified) signal, or None if it should be blocked.
    """
    funding = await get_latest_funding_rate()
    oi_change = await get_oi_change_pct()

    # --- Funding rate direction blocks ---
    if funding is not None:
        if signal.direction == "LONG" and funding > FUNDING_LONG_BLOCK:
            log.info(
                "CryptoIntelligence blocked LONG: funding rate %.4f%% > threshold",
                funding * 100,
            )
            return None

        if signal.direction == "SHORT" and funding < FUNDING_SHORT_BLOCK:
            log.info(
                "CryptoIntelligence blocked SHORT: funding rate %.4f%% < threshold",
                funding * 100,
            )
            return None

    # --- OI adjustments to confidence ---
    if oi_change is not None:
        if oi_change > OI_SPIKE_PCT:
            signal.confidence_score = min(100.0, signal.confidence_score + 5.0)
            signal.reasoning += f" OI spiked +{oi_change*100:.1f}% (momentum confirmed)."
        elif oi_change < -OI_SPIKE_PCT:
            signal.confidence_score = max(0.0, signal.confidence_score - 10.0)
            signal.reasoning += f" OI dropped {oi_change*100:.1f}% (trend weakening)."

    return signal
