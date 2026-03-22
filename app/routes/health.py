from datetime import datetime, timezone
from fastapi import APIRouter
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.tables import Candle, SystemState
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    async with AsyncSessionLocal() as session:
        candle_count = (await session.execute(
            select(func.count(Candle.id)).where(Candle.symbol == settings.SYMBOL)
        )).scalar()

        cb = await session.get(SystemState, "circuit_breaker_active")
        cb_active = cb.value == "true" if cb else False
        cb_until = (await session.get(SystemState, "circuit_breaker_until"))
        daily_loss = (await session.get(SystemState, "daily_loss_pct"))

    return {
        "status": "ok",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "symbol": settings.SYMBOL,
        "candles_stored": candle_count,
        "circuit_breaker_active": cb_active,
        "circuit_breaker_until": cb_until.value if cb_until else None,
        "daily_loss_pct": float(daily_loss.value) if daily_loss else 0.0,
    }
