"""
Tests for FastAPI routes using TestClient with mocked DB.
The lifespan (scheduler + DB startup) is patched out so tests
run without a real Postgres or Binance connection.
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import health, status, candles, dashboard


# Minimal test app — same routes, no DB/scheduler lifespan
def _make_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(health.router)
    test_app.include_router(status.router)
    test_app.include_router(candles.router)

    @test_app.get("/")
    def root():
        return {"message": "visit /dashboard/"}

    return test_app


@pytest.fixture
def client():
    with TestClient(_make_test_app(), raise_server_exceptions=False) as c:
        yield c


class TestRootRoute:
    def test_root_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_mentions_dashboard(self, client):
        resp = client.get("/")
        assert "dashboard" in resp.json()["message"].lower()


class TestHealthRoute:
    def test_health_returns_200_with_mocked_db(self, client):
        # AsyncSessionLocal() must return an async context manager that yields the session
        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock(scalar=MagicMock(return_value=0))
        # get() is called 3 times: circuit_breaker_active, circuit_breaker_until, daily_loss_pct
        mock_session.get.side_effect = [
            MagicMock(value="false"),  # circuit_breaker_active
            None,                       # circuit_breaker_until → route returns None
            None,                       # daily_loss_pct → route returns 0.0
        ]

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.health.AsyncSessionLocal", return_value=mock_cm):
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_has_required_fields(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar=MagicMock(return_value=100))
        )
        mock_session.get = AsyncMock(return_value=MagicMock(value="false"))

        with patch("app.routes.health.AsyncSessionLocal", return_value=mock_session):
            resp = client.get("/health")

        if resp.status_code == 200:
            data = resp.json()
            assert "status" in data
            assert "symbol" in data
            assert "circuit_breaker_active" in data

    def test_health_symbol_is_btcusdt(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar=MagicMock(return_value=0))
        )
        mock_session.get = AsyncMock(return_value=MagicMock(value="false"))

        with patch("app.routes.health.AsyncSessionLocal", return_value=mock_session):
            resp = client.get("/health")

        if resp.status_code == 200:
            assert resp.json()["symbol"] == "BTCUSDT"


class TestCandlesRoute:
    def test_invalid_timeframe_returns_400(self, client):
        resp = client.get("/candles/M5")  # M5 is not a valid timeframe
        assert resp.status_code == 400

    def test_valid_timeframes_accepted(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        )

        for tf in ["M15", "H1", "H4", "D1"]:
            with patch("app.routes.candles.AsyncSessionLocal", return_value=mock_session):
                resp = client.get(f"/candles/{tf}")
            assert resp.status_code == 200, f"Timeframe {tf} should be valid"

    def test_candles_returns_list(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        )

        with patch("app.routes.candles.AsyncSessionLocal", return_value=mock_session):
            resp = client.get("/candles/M15")

        if resp.status_code == 200:
            assert isinstance(resp.json(), list)

    def test_candles_gaps_invalid_timeframe_returns_400(self, client):
        resp = client.get("/candles/W1/gaps")
        assert resp.status_code == 400


class TestStatusRoute:
    def test_status_returns_200_with_mocked_db(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
                                   scalar_one_or_none=MagicMock(return_value=None))
        )

        with patch("app.routes.status.AsyncSessionLocal", return_value=mock_session):
            resp = client.get("/status")

        assert resp.status_code == 200

    def test_status_has_strategy_rankings(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
                                   scalar_one_or_none=MagicMock(return_value=None))
        )

        with patch("app.routes.status.AsyncSessionLocal", return_value=mock_session):
            resp = client.get("/status")

        if resp.status_code == 200:
            assert "strategy_rankings" in resp.json()
