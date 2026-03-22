"""
CandleIngestor
--------------
Fetches BTCUSDT perpetual futures candles from Binance via ccxt,
plus funding rate and open interest snapshots.
All data is upserted into Postgres.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import ccxt.async_support as ccxt
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tables import Candle, FundingRate, OpenInterest

log = logging.getLogger(__name__)

TIMEFRAMES = {
    "M15": "15m",
    "H1":  "1h",
    "H4":  "4h",
    "D1":  "1d",
}
LIMIT = 200  # bars per fetch


def _make_exchange() -> ccxt.binanceusdm:
    return ccxt.binanceusdm({"options": {"defaultType": "future"}})


async def fetch_candles(tf_key: str) -> None:
    """Fetch 200 closed bars for one timeframe and upsert into candles table."""
    ccxt_tf = TIMEFRAMES[tf_key]
    exchange = _make_exchange()
    try:
        raw = await exchange.fetch_ohlcv(settings.SYMBOL, timeframe=ccxt_tf, limit=LIMIT + 1)
        # Drop the last bar — it may still be forming
        raw = raw[:-1]

        rows = []
        for bar in raw:
            ts_open = datetime.fromtimestamp(bar[0] / 1000, tz=timezone.utc)
            # close_time approximation: open_time + timeframe duration - 1ms
            rows.append({
                "symbol": settings.SYMBOL,
                "timeframe": tf_key,
                "open_time": ts_open,
                "open": bar[1],
                "high": bar[2],
                "low": bar[3],
                "close": bar[4],
                "volume": bar[5],
                "close_time": ts_open,  # will be updated below
            })

        async with AsyncSessionLocal() as session:
            if rows:
                stmt = pg_insert(Candle).values(rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "timeframe", "open_time"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                    },
                )
                await session.execute(stmt)
                await session.commit()
        log.info("Candles upserted: %s %s (%d bars)", settings.SYMBOL, tf_key, len(rows))

    except Exception as e:
        log.error("fetch_candles %s failed: %s", tf_key, e)
    finally:
        await exchange.close()


async def fetch_funding_rate() -> None:
    """Fetch recent funding rate history and upsert."""
    exchange = _make_exchange()
    try:
        data = await exchange.fetch_funding_rate_history(settings.SYMBOL, limit=10)
        rows = []
        for item in data:
            rows.append({
                "symbol": settings.SYMBOL,
                "funding_rate": float(item["fundingRate"]),
                "funding_time": datetime.fromtimestamp(item["timestamp"] / 1000, tz=timezone.utc),
            })

        async with AsyncSessionLocal() as session:
            if rows:
                stmt = pg_insert(FundingRate).values(rows)
                stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "funding_time"])
                await session.execute(stmt)
                await session.commit()
        log.info("Funding rates upserted: %d rows", len(rows))

    except Exception as e:
        log.error("fetch_funding_rate failed: %s", e)
    finally:
        await exchange.close()


async def fetch_open_interest() -> None:
    """Fetch current open interest snapshot and insert."""
    exchange = _make_exchange()
    try:
        oi = await exchange.fetch_open_interest(settings.SYMBOL)
        now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
        row = {
            "symbol": settings.SYMBOL,
            "open_interest": float(oi["openInterestAmount"]),
            "timestamp": now,
        }
        async with AsyncSessionLocal() as session:
            stmt = pg_insert(OpenInterest).values([row])
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
            await session.execute(stmt)
            await session.commit()
        log.info("Open interest upserted: %s", row["open_interest"])

    except Exception as e:
        log.error("fetch_open_interest failed: %s", e)
    finally:
        await exchange.close()


async def refresh_all() -> None:
    """Run all ingestion tasks concurrently."""
    await asyncio.gather(
        fetch_candles("M15"),
        fetch_candles("H1"),
        fetch_candles("H4"),
        fetch_candles("D1"),
        fetch_funding_rate(),
        fetch_open_interest(),
        return_exceptions=True,
    )
    log.info("Full candle refresh complete.")
