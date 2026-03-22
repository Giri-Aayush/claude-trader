"""
FeedbackController
------------------
Reads recent outcomes and recalculates performance scores for each strategy.
Performance score = composite of win rate, Sharpe, and recency weighting.
Called after OutcomeDetector resolves trades or on a scheduled basis.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.tables import Outcome, Signal, StrategyPerformance
from app.services.metrics_calculator import compute_metrics

log = logging.getLogger(__name__)

LOOKBACK_DAYS = 30


async def update_performance_scores() -> None:
    """Recompute performance_score for all strategies from recent outcomes."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    strategy_names = ["liquidity_sweep", "trend_continuation", "breakout_expansion", "ema_momentum"]

    async with AsyncSessionLocal() as session:
        for strategy_name in strategy_names:
            # Fetch all resolved outcomes for this strategy in the lookback window
            result = await session.execute(
                select(Outcome.pnl_pct)
                .join(Signal, Outcome.signal_id == Signal.id)
                .where(
                    Signal.strategy_name == strategy_name,
                    Outcome.resolved_at >= cutoff,
                )
                .order_by(Outcome.resolved_at)
            )
            pnl_list = [float(row) for row in result.scalars().all()]

            if not pnl_list:
                continue

            metrics = compute_metrics(pnl_list)

            # Composite score: blend of win rate (40%), sharpe (40%), expectancy (20%)
            win_score = metrics["win_rate"] * 100 * 0.40
            sharpe_clamped = max(-2, min(metrics["sharpe"], 5))  # clamp extreme values
            sharpe_score = ((sharpe_clamped + 2) / 7) * 100 * 0.40
            exp_score = max(0, min(metrics["expectancy"] * 1000, 100)) * 0.20
            perf_score = round(win_score + sharpe_score + exp_score, 2)

            # Flag suspicious metrics (likely data leak) — lower score
            if metrics["is_suspicious"]:
                log.warning(
                    "Strategy %s has suspicious metrics (WR=%.1f%%, Sharpe=%.2f). Penalising.",
                    strategy_name, metrics["win_rate"] * 100, metrics["sharpe"],
                )
                perf_score = min(perf_score, 20.0)

            perf_result = await session.execute(
                select(StrategyPerformance).where(
                    StrategyPerformance.strategy_name == strategy_name
                )
            )
            perf = perf_result.scalar_one_or_none()
            if perf:
                perf.win_rate = metrics["win_rate"]
                perf.sharpe_ratio = metrics["sharpe"]
                wins = [p for p in pnl_list if p > 0]
                losses = [abs(p) for p in pnl_list if p < 0]
                avg_win = sum(wins) / len(wins) if wins else 0.0
                avg_loss = sum(losses) / len(losses) if losses else 1.0
                perf.avg_rr = round(avg_win / avg_loss, 4) if avg_loss > 0 else 2.0
                perf.performance_score = perf_score
                perf.total_trades = metrics["total_trades"]
                perf.last_updated = datetime.now(tz=timezone.utc)
                log.info(
                    "Updated %s: score=%.1f, WR=%.1f%%, Sharpe=%.2f, trades=%d",
                    strategy_name, perf_score, metrics["win_rate"] * 100,
                    metrics["sharpe"], metrics["total_trades"],
                )

        await session.commit()
