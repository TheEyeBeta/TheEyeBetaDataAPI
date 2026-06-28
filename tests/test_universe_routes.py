"""Tests for universe cap-rank and cap-event routes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_market_data_service
from app.auth.scopes import SCOPE_SYMBOLS_READ
from app.core.config import settings
from app.main import app
from app.schemas.market import (
    CapEventResponse,
    CapEventsResponse,
    UniverseActiveResponse,
    UniverseCapEntryResponse,
)


class _FakeMarketDataService:
    def get_universe_active(self, min_market_cap: float, limit: int) -> UniverseActiveResponse:
        return UniverseActiveResponse(
            as_of_date=date(2026, 6, 20),
            entries=[
                UniverseCapEntryResponse(
                    symbol="AAPL",
                    as_of_date=date(2026, 6, 20),
                    market_cap=3_000_000_000_000,
                    close_price=190.0,
                ),
            ],
        )

    def get_cap_events(self, since: date | None, limit: int) -> CapEventsResponse:
        return CapEventsResponse(
            events=[
                CapEventResponse(
                    id=1,
                    trade_date=date(2026, 6, 20),
                    symbol="NEWCO",
                    event_type="entered_universe",
                    universe_updated=True,
                ),
            ],
        )


def _make_user_token(scopes: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "user-universe",
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }
    return jwt.encode(payload, settings.user_jwt_secret, algorithm=settings.user_jwt_algorithm)


def test_universe_active_returns_rows() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeMarketDataService()
    client = TestClient(app)
    token = _make_user_token(["market:read"])

    response = client.get("/api/v1/universe/active", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["entries"][0]["symbol"] == "AAPL"
    app.dependency_overrides.clear()


def test_universe_active_requires_market_read_scope() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeMarketDataService()
    client = TestClient(app)
    token = _make_user_token([SCOPE_SYMBOLS_READ])

    response = client.get("/api/v1/universe/active", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_cap_events_returns_rows() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeMarketDataService()
    client = TestClient(app)
    token = _make_user_token(["market:read"])

    response = client.get("/api/v1/universe/cap-events", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["events"][0]["symbol"] == "NEWCO"
    app.dependency_overrides.clear()


def test_universe_active_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/universe/active")
    assert response.status_code == 401
