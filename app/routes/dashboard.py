from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta

from app.database import AsyncSessionLocal
from app.models.tables import Signal, Outcome, StrategyPerformance, SystemState
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard/", response_class=HTMLResponse)
async def dashboard(request: Request):
    async with AsyncSessionLocal() as session:
        cutoff_7d = datetime.now(tz=timezone.utc) - timedelta(days=7)

        # Strategy performance
        perfs = (await session.execute(
            select(StrategyPerformance).order_by(StrategyPerformance.performance_score.desc())
        )).scalars().all()

        # Recent signals (last 50)
        signals = (await session.execute(
            select(Signal).order_by(Signal.generated_at.desc()).limit(50)
        )).scalars().all()

        # Recent outcomes (for equity curve)
        outcomes = (await session.execute(
            select(Outcome).order_by(Outcome.resolved_at).limit(200)
        )).scalars().all()

        # System state
        cb = await session.get(SystemState, "circuit_breaker_active")
        cb_active = cb.value == "true" if cb else False
        daily_loss = await session.get(SystemState, "daily_loss_pct")

        # 7d summary
        wins_7d = (await session.execute(
            select(func.count(Outcome.id)).where(
                Outcome.result == "WIN",
                Outcome.resolved_at >= cutoff_7d,
            )
        )).scalar() or 0
        total_7d = (await session.execute(
            select(func.count(Outcome.id)).where(Outcome.resolved_at >= cutoff_7d)
        )).scalar() or 0
        win_rate_7d = (wins_7d / total_7d * 100) if total_7d > 0 else 0

    # Build equity curve data
    equity = [100.0]
    for o in outcomes:
        equity.append(round(equity[-1] * (1 + float(o.pnl_pct)), 2))
    equity_labels = list(range(len(equity)))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "symbol": settings.SYMBOL,
        "perfs": [
            {
                "name": p.strategy_name.replace("_", " ").title(),
                "score": round(float(p.performance_score), 1),
                "win_rate": round(float(p.win_rate) * 100, 1),
                "sharpe": round(float(p.sharpe_ratio or 0), 2),
                "trades": p.total_trades,
                "consec_losses": p.consecutive_losses,
            }
            for p in perfs
        ],
        "signals": [
            {
                "id": s.id,
                "strategy": s.strategy_name.replace("_", " ").title(),
                "direction": s.direction,
                "entry": float(s.entry_price),
                "sl": float(s.stop_loss),
                "tp": float(s.take_profit),
                "confidence": float(s.confidence_score),
                "status": s.status,
                "generated_at": s.generated_at.strftime("%Y-%m-%d %H:%M") if s.generated_at else "",
            }
            for s in signals
        ],
        "circuit_breaker": cb_active,
        "daily_loss_pct": round(float(daily_loss.value) * 100 if daily_loss else 0, 2),
        "win_rate_7d": round(win_rate_7d, 1),
        "total_trades_7d": total_7d,
        "equity_data": equity,
        "equity_labels": equity_labels,
    })


@router.get("/chart/", response_class=HTMLResponse)
async def chart(request: Request, tf: str = "M15"):
    return templates.TemplateResponse("chart.html", {
        "request": request,
        "symbol": settings.SYMBOL,
        "tf": tf,
    })
