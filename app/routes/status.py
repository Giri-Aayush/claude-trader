from fastapi import APIRouter
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.tables import StrategyPerformance, Signal, BacktestResult

router = APIRouter()


@router.get("/status")
async def status():
    async with AsyncSessionLocal() as session:
        perfs = (await session.execute(
            select(StrategyPerformance).order_by(StrategyPerformance.performance_score.desc())
        )).scalars().all()

        last_signal = (await session.execute(
            select(Signal).order_by(Signal.generated_at.desc()).limit(1)
        )).scalar_one_or_none()

        last_bt = (await session.execute(
            select(BacktestResult).order_by(BacktestResult.run_at.desc()).limit(1)
        )).scalar_one_or_none()

    return {
        "strategy_rankings": [
            {
                "name": p.strategy_name,
                "score": float(p.performance_score),
                "win_rate": float(p.win_rate),
                "sharpe": float(p.sharpe_ratio or 0),
                "total_trades": p.total_trades,
                "consecutive_losses": p.consecutive_losses,
            }
            for p in perfs
        ],
        "last_signal": {
            "id": last_signal.id,
            "strategy": last_signal.strategy_name,
            "direction": last_signal.direction,
            "entry": float(last_signal.entry_price),
            "status": last_signal.status,
            "generated_at": last_signal.generated_at.isoformat(),
        } if last_signal else None,
        "last_backtest_at": last_bt.run_at.isoformat() if last_bt else None,
    }
