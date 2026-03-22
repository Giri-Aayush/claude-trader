"""
Claude BTC Perp Trader — FastAPI entrypoint.
"""

import logging
import os
import sqlalchemy
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import engine
from app.models import tables  # noqa — ensures models are registered
from app.scheduler import setup_scheduler
from app.routes import health, status, candles, dashboard
from app.services.candle_ingestor import refresh_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger(__name__)


async def _run_migrations() -> None:
    """Run init.sql on startup — safe to re-run (CREATE TABLE IF NOT EXISTS).
    Executes each statement individually because asyncpg rejects multi-statement strings.
    """
    sql_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "init.sql")
    try:
        with open(sql_path) as f:
            sql = f.read()
        # Strip comments and split into individual statements
        statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
        async with engine.begin() as conn:
            for stmt in statements:
                await conn.execute(sqlalchemy.text(stmt))
        log.info("Migrations applied (%d statements).", len(statements))
    except Exception as e:
        log.warning("Migration step skipped or failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Claude BTC Perp Trader...")

    await _run_migrations()

    # Initial candle refresh on startup
    try:
        await refresh_all()
    except Exception as e:
        log.warning("Initial candle refresh failed (DB may not be ready): %s", e)

    # Start scheduler
    scheduler = setup_scheduler()
    scheduler.start()
    log.info("Scheduler started.")

    yield

    scheduler.shutdown()
    await engine.dispose()
    log.info("Shutdown complete.")


app = FastAPI(
    title="Claude BTC Perp Trader",
    description="Autonomous BTCUSDT perpetual futures signal system",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(status.router)
app.include_router(candles.router)
app.include_router(dashboard.router)
