import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta

from app.database import AsyncSessionLocal
from app.models.tables import Signal, Outcome, StrategyPerformance, SystemState, FundingRate, OpenInterest
from app.config import settings

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        return await _dashboard_data(request)
    except Exception as e:
        log.error("Dashboard DB error: %s", e)
        return HTMLResponse(
            content=_db_error_page(str(e)),
            status_code=503,
        )


async def _dashboard_data(request: Request) -> HTMLResponse:
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

        # Recent outcomes (for equity curve) — fetch most recent 200 then reverse for chronological order
        outcomes = list(reversed((await session.execute(
            select(Outcome).order_by(Outcome.resolved_at.desc()).limit(200)
        )).scalars().all()))

        # System state
        cb = await session.get(SystemState, "circuit_breaker_active")
        cb_active = cb.value == "true" if cb else False
        daily_loss = await session.get(SystemState, "daily_loss_pct")

        # Latest funding rate
        latest_fr = (await session.execute(
            select(FundingRate).where(FundingRate.symbol == settings.SYMBOL)
            .order_by(FundingRate.funding_time.desc()).limit(1)
        )).scalar_one_or_none()

        # Latest open interest
        latest_oi = (await session.execute(
            select(OpenInterest).where(OpenInterest.symbol == settings.SYMBOL)
            .order_by(OpenInterest.timestamp.desc()).limit(1)
        )).scalar_one_or_none()

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
        "funding_rate": round(float(latest_fr.funding_rate) * 100, 4) if latest_fr else None,
        "open_interest": round(float(latest_oi.open_interest) / 1e9, 2) if latest_oi else None,
    })


def _db_error_page(detail: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><title>Claude Trader — DB not ready</title>
<style>
  body {{ font-family: monospace; background: #0f0f0f; color: #e0e0e0;
         display: flex; align-items: center; justify-content: center;
         height: 100vh; margin: 0; }}
  .box {{ max-width: 560px; padding: 2rem; border: 1px solid #333;
          border-radius: 8px; }}
  h2 {{ color: #f59e0b; margin-top: 0; }}
  code {{ background: #1a1a1a; padding: .2em .4em; border-radius: 4px;
          font-size: .85em; word-break: break-all; }}
  ol {{ line-height: 1.8; }}
</style>
</head>
<body>
<div class="box">
  <h2>Database not reachable</h2>
  <p>The app started but cannot connect to Postgres. Most likely
  <code>DATABASE_URL</code> is not set in your Render environment.</p>
  <ol>
    <li>Go to <strong>Render dashboard → claude-trader → Environment</strong></li>
    <li>Add <code>DATABASE_URL</code> — copy the <em>Internal Connection String</em>
        from your <strong>traderdb</strong> Render database page</li>
    <li>Save &amp; redeploy (Render redeploys automatically on env changes)</li>
  </ol>
  <p style="color:#6b7280;font-size:.8em">Error: {detail}</p>
</div>
</body>
</html>"""


@router.get("/chart/", response_class=HTMLResponse)
async def chart(request: Request, tf: str = "M15"):
    return templates.TemplateResponse("chart.html", {
        "request": request,
        "symbol": settings.SYMBOL,
        "tf": tf,
    })
