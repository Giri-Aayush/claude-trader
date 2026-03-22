from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.tables import Candle
from app.config import settings

router = APIRouter()

VALID_TIMEFRAMES = {"M15", "H1", "H4", "D1"}


@router.get("/candles/{tf}")
async def get_candles(tf: str, limit: int = 200):
    if tf not in VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Use one of: {VALID_TIMEFRAMES}")

    limit = min(limit, 500)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Candle)
            .where(Candle.symbol == settings.SYMBOL, Candle.timeframe == tf)
            .order_by(Candle.open_time.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

    return [
        {
            "time": int(r.open_time.timestamp()),
            "open":  float(r.open),
            "high":  float(r.high),
            "low":   float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
        }
        for r in reversed(rows)
    ]


@router.get("/candles/{tf}/gaps")
async def get_candle_gaps(tf: str):
    """Returns a list of missing bar timestamps for data quality monitoring."""
    if tf not in VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail="Invalid timeframe.")

    tf_minutes = {"M15": 15, "H1": 60, "H4": 240, "D1": 1440}
    interval_min = tf_minutes[tf]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Candle.open_time)
            .where(Candle.symbol == settings.SYMBOL, Candle.timeframe == tf)
            .order_by(Candle.open_time)
        )
        times = [r for r in result.scalars().all()]

    if len(times) < 2:
        return {"gaps": []}

    from datetime import timedelta
    gaps = []
    for i in range(1, len(times)):
        expected_gap = timedelta(minutes=interval_min)
        actual_gap = times[i] - times[i - 1]
        if actual_gap > expected_gap * 1.5:
            gaps.append({
                "from": times[i - 1].isoformat(),
                "to": times[i].isoformat(),
                "missing_bars": int(actual_gap / expected_gap) - 1,
            })

    return {"gaps": gaps, "total_bars": len(times)}
