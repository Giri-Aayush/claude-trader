"""
StrategySelector
----------------
Loads candle data from Postgres into DataFrames, runs all active strategies,
and returns the highest-confidence candidate signal (if any).

Strategies are weighted by their performance_score from the DB.
Only strategies above a minimum score threshold are run.
"""

import logging
from typing import Optional

import pandas as pd
from sqlalchemy import select, desc

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tables import Candle, StrategyPerformance
from app.strategies.base import CandidateSignal
from app.strategies.liquidity_sweep import LiquiditySweepStrategy
from app.strategies.trend_continuation import TrendContinuationStrategy
from app.strategies.breakout_expansion import BreakoutExpansionStrategy
from app.strategies.ema_momentum import EmaMomentumStrategy

log = logging.getLogger(__name__)

ALL_STRATEGIES = [
    LiquiditySweepStrategy(),
    TrendContinuationStrategy(),
    BreakoutExpansionStrategy(),
    EmaMomentumStrategy(),
]

MIN_PERFORMANCE_SCORE = 30.0  # strategies below this are suspended
CANDLE_LIMIT = 220            # fetch slightly more than needed for indicator warmup


async def _load_candles() -> dict[str, pd.DataFrame]:
    """Load the most recent CANDLE_LIMIT closed bars for all timeframes."""
    frames = {}
    async with AsyncSessionLocal() as session:
        for tf in ["M15", "H1", "H4", "D1"]:
            result = await session.execute(
                select(Candle)
                .where(Candle.symbol == settings.SYMBOL, Candle.timeframe == tf)
                .order_by(desc(Candle.open_time))
                .limit(CANDLE_LIMIT)
            )
            rows = result.scalars().all()
            if not rows:
                continue
            df = pd.DataFrame([{
                "open_time": r.open_time,
                "open":  float(r.open),
                "high":  float(r.high),
                "low":   float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            } for r in reversed(rows)])  # oldest first
            frames[tf] = df
    return frames


async def _get_performance_scores() -> dict[str, float]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(StrategyPerformance))
        rows = result.scalars().all()
        return {r.strategy_name: float(r.performance_score) for r in rows}


async def run() -> Optional[CandidateSignal]:
    """
    Load candles, run all strategies above the min score, return the
    highest-confidence signal or None.
    """
    candles = await _load_candles()
    if not candles:
        log.warning("No candle data available — skipping strategy run.")
        return None

    scores = await _get_performance_scores()
    candidates: list[CandidateSignal] = []

    for strategy in ALL_STRATEGIES:
        score = scores.get(strategy.name, 50.0)
        if score < MIN_PERFORMANCE_SCORE:
            log.info("Strategy %s suspended (score=%.1f).", strategy.name, score)
            continue

        try:
            signal = strategy.generate(candles)
            if signal is not None:
                # Weight confidence by performance score
                signal.confidence_score = round(
                    signal.confidence_score * (score / 100), 2
                )
                candidates.append(signal)
                log.info(
                    "Strategy %s generated %s signal (conf=%.1f).",
                    strategy.name, signal.direction, signal.confidence_score,
                )
        except Exception as e:
            log.error("Strategy %s raised exception: %s", strategy.name, e)

    if not candidates:
        return None

    # Return highest confidence signal
    return max(candidates, key=lambda s: s.confidence_score)
