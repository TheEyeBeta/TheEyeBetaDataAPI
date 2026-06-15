"""Tests for macro indicator / regime routes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_macro_service
from app.core.config import settings
from app.main import app
from app.schemas.macro import (
    MacroLatestItem,
    MacroLatestResponse,
    MacroObservationPoint,
    MacroRegimeResponse,
    MacroSeriesDetailResponse,
    MacroSeriesListResponse,
    MacroSeriesSummary,
)

MACRO_PREFIX = "/v1/macro"


def _make_user_token(scopes: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "user-123",
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }
    return jwt.encode(payload, settings.user_jwt_secret, algorithm=settings.user_jwt_algorithm)


class _FakeMacroService:
    def __init__(self, *, detail_exists: bool = True, regime_exists: bool = True) -> None:
        self._detail_exists = detail_exists
        self._regime_exists = regime_exists

    def list_series(self, *, category: str | None = None) -> MacroSeriesListResponse:  # noqa: ARG002
        return MacroSeriesListResponse(
            count=1,
            series=[
                MacroSeriesSummary(
                    code="DGS10",
                    name="10-Year Treasury Constant Maturity",
                    category="rates",
                    frequency="daily",
                    units="Percent",
                    source="FRED",
                    latest_value=4.25,
                    latest_date=date(2026, 6, 15),
                    observation_count=5000,
                    in_registry=True,
                )
            ],
        )

    def get_series(self, *, code: str, start=None, end=None, limit: int = 500):  # noqa: ANN001, ARG002
        if not self._detail_exists:
            return None
        return MacroSeriesDetailResponse(
            code=code,
            name="10-Year Treasury Constant Maturity",
            category="rates",
            frequency="daily",
            units="Percent",
            source="FRED",
            in_registry=True,
            observation_count=1,
            start=date(2026, 3, 17),
            end=None,
            observations=[MacroObservationPoint(date=date(2026, 6, 15), value=4.25)],
        )

    def get_latest(self, *, codes=None) -> MacroLatestResponse:  # noqa: ANN001, ARG002
        return MacroLatestResponse(
            count=1,
            observations=[
                MacroLatestItem(
                    code="DGS10",
                    name="10-Year Treasury Constant Maturity",
                    category="rates",
                    units="Percent",
                    date=date(2026, 6, 15),
                    value=4.25,
                    source="FRED",
                )
            ],
        )

    def get_regime(self) -> MacroRegimeResponse | None:
        if not self._regime_exists:
            return None
        return MacroRegimeResponse(as_of_date=date(2026, 6, 15), vix=14.2, rate_environment="restrictive")


def test_macro_series_requires_bearer_token() -> None:
    client = TestClient(app)
    response = client.get(f"{MACRO_PREFIX}/series")
    assert response.status_code == 401


def test_macro_series_forbidden_without_scope() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService()
    client = TestClient(app)
    token = _make_user_token(scopes=["advisor:read"])
    response = client.get(f"{MACRO_PREFIX}/series", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_macro_series_list_ok() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{MACRO_PREFIX}/series", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["series"][0]["code"] == "DGS10"
    app.dependency_overrides.clear()


def test_macro_series_detail_ok() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{MACRO_PREFIX}/series/DGS10", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["observations"][0]["value"] == 4.25
    app.dependency_overrides.clear()


def test_macro_series_detail_not_found() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService(detail_exists=False)
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{MACRO_PREFIX}/series/NOPE", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    app.dependency_overrides.clear()


def test_macro_latest_ok() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(
        f"{MACRO_PREFIX}/latest?codes=DGS10", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["observations"][0]["code"] == "DGS10"
    app.dependency_overrides.clear()


def test_macro_regime_ok() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{MACRO_PREFIX}/regime", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["rate_environment"] == "restrictive"
    app.dependency_overrides.clear()


def test_macro_regime_not_found_when_empty() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService(regime_exists=False)
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{MACRO_PREFIX}/regime", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_macro_legacy_api_v1_alias_ok() -> None:
    app.dependency_overrides[get_macro_service] = lambda: _FakeMacroService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get("/api/v1/macro/series", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["series"][0]["code"] == "DGS10"
    app.dependency_overrides.clear()
