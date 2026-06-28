"""Tests for sector aggregate routes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_market_data_service
from app.auth.scopes import SCOPE_SYMBOLS_READ
from app.core.config import settings
from app.main import app
from app.schemas.market import SectorDailyEntryResponse, SectorDailyResponse


class _FakeMarketDataService:
    def get_sector_daily(self, sector: str | None, limit: int) -> SectorDailyResponse:
        return SectorDailyResponse(
            sectors=[
                SectorDailyEntryResponse(
                    sector="Technology",
                    as_of_date=date(2026, 6, 20),
                    n_instruments=42,
                    rotation_rank=1,
                ),
            ],
        )


def _make_user_token(scopes: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "user-sectors",
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }
    return jwt.encode(payload, settings.user_jwt_secret, algorithm=settings.user_jwt_algorithm)


def test_sector_daily_returns_rows() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeMarketDataService()
    client = TestClient(app)
    token = _make_user_token(["market:read"])

    response = client.get("/api/v1/sectors/daily", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["sectors"][0]["sector"] == "Technology"
    assert body["sectors"][0]["rotation_rank"] == 1
    app.dependency_overrides.clear()


def test_sector_daily_requires_market_read_scope() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeMarketDataService()
    client = TestClient(app)
    token = _make_user_token([SCOPE_SYMBOLS_READ])

    response = client.get("/api/v1/sectors/daily", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_sector_daily_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/sectors/daily")
    assert response.status_code == 401
