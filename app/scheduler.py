"""
APScheduler configuration.
All jobs are registered here and started with the FastAPI lifespan.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services import candle_ingestor, outcome_detector, feedback_controller
from app.services import backtest_runner, param_optimizer, signal_pipeline, telegram_notifier
from app.services.metrics_calculator import compute_metrics

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


async def _health_digest() -> None:
    """Build and send a daily health digest to Telegram."""
    from sqlalchemy import select, func
    from datetime import datetime, timezone, timedelta
    from app.database import AsyncSessionLocal
    from app.models.tables import Outcome, Signal, StrategyPerformance, SystemState

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    async with AsyncSessionLocal() as session:
        outcomes = await session.execute(
            select(Outcome.pnl_pct).join(Signal, Outcome.signal_id == Signal.id)
            .where(Outcome.resolved_at >= cutoff)
        )
        pnl_list = [float(r) for r in outcomes.scalars().all()]
        metrics_7d = compute_metrics(pnl_list)

        total_signals = (await session.execute(
            select(func.count(Signal.id)).where(Signal.generated_at >= cutoff)
        )).scalar()

        top_perf = (await session.execute(
            select(StrategyPerformance.strategy_name)
            .order_by(StrategyPerformance.performance_score.desc())
            .limit(1)
        )).scalar()

        cb = (await session.get(SystemState, "circuit_breaker_active"))
        cb_active = cb.value == "true" if cb else False

    await telegram_notifier.send_health_digest({
        "win_rate_7d": metrics_7d["win_rate"],
        "sharpe_7d": metrics_7d["sharpe"],
        "max_drawdown": metrics_7d["max_drawdown"],
        "total_signals_7d": total_signals or 0,
        "circuit_breaker": cb_active,
        "top_strategy": top_perf or "N/A",
    })


def setup_scheduler() -> AsyncIOScheduler:
    # Every 15 min: refresh candles + funding rate + OI (matches M15 candle close)
    scheduler.add_job(
        candle_ingestor.refresh_all,
        IntervalTrigger(minutes=15),
        id="candle_refresh",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # Every 15 min (offset 2 min): run signal pipeline
    scheduler.add_job(
        signal_pipeline.run,
        IntervalTrigger(minutes=15, start_date="2024-01-01 00:02:00"),
        id="signal_pipeline",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Every 90 seconds: check open signal outcomes
    scheduler.add_job(
        outcome_detector.check_outcomes,
        IntervalTrigger(seconds=90),
        id="outcome_detector",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # Every 4 hours: run backtests
    scheduler.add_job(
        backtest_runner.run_backtests,
        IntervalTrigger(hours=4),
        id="backtest_runner",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Every 6 hours: parameter optimization
    scheduler.add_job(
        param_optimizer.run_optimization,
        IntervalTrigger(hours=6),
        id="param_optimizer",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Daily 03:00 UTC: feedback controller + data retention
    scheduler.add_job(
        feedback_controller.update_performance_scores,
        CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="feedback_controller",
        replace_existing=True,
    )

    # Daily 06:00 UTC: health digest
    scheduler.add_job(
        _health_digest,
        CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="health_digest",
        replace_existing=True,
    )

    log.info("APScheduler configured with %d jobs.", len(scheduler.get_jobs()))
    return scheduler
