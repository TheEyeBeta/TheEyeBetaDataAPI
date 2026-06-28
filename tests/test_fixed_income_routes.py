"""Tests for fixed-income regime routes."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_fixed_income_service
from app.core.config import settings
from app.main import app
from app.schemas.fixed_income import (
    FixedIncomeCurveMetricResponse,
    FixedIncomeETFProxyPriceResponse,
    FixedIncomeHistoryResponse,
    FixedIncomeRegimeResponse,
    FixedIncomeSignalResponse,
    FixedIncomeSignalsResponse,
)

PREFIX = "/api/v1/fixed-income"


def _make_user_token(scopes: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user-123",
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }
    return jwt.encode(payload, settings.user_jwt_secret, algorithm=settings.user_jwt_algorithm)


class _FakeFixedIncomeService:
    def __init__(self, *, regime_exists: bool = True, include_proxies: bool = True) -> None:
        self._regime_exists = regime_exists
        self._include_proxies = include_proxies

    def get_regime(self) -> FixedIncomeRegimeResponse | None:
        if not self._regime_exists:
            return None
        return FixedIncomeRegimeResponse(
            latest=FixedIncomeCurveMetricResponse(
                date=date(2026, 6, 15),
                country="US",
                currency="USD",
                y_10y=4.25,
                y_2y=4.80,
                spread_10y_2y=-0.55,
                spread_10y_3m=-1.10,
                real_yield_10y=2.05,
                high_yield_spread=4.60,
                curve_regime="deep_inversion",
                rate_regime="stable",
                credit_regime="mild_credit_stress",
                bond_environment_score=38,
                bond_environment_label="equity_hostile",
                source="fred+yfinance",
            ),
            signals=[
                FixedIncomeSignalResponse(
                    date=date(2026, 6, 15),
                    country="US",
                    signal_name="curve_inversion",
                    value=-1.10,
                    strength="strong",
                    direction="risk_off",
                    interpretation="Curve is inverted.",
                )
            ],
            etf_proxies=(
                [
                    FixedIncomeETFProxyPriceResponse(
                        symbol="TLT",
                        name="iShares 20+ Year Treasury Bond ETF",
                        date=date(2026, 6, 15),
                        close=90.12,
                        change_1d_pct=-0.42,
                        source="yfinance:fixed_income_proxy",
                    )
                ]
                if self._include_proxies
                else []
            ),
        )

    def get_history(self, *, start=None, end=None, limit: int = 252):  # noqa: ANN001, ARG002
        return FixedIncomeHistoryResponse(
            count=1,
            metrics=[
                FixedIncomeCurveMetricResponse(
                    date=date(2026, 6, 15),
                    country="US",
                    bond_environment_score=38,
                    bond_environment_label="equity_hostile",
                )
            ],
        )

    def get_signals(self, *, limit: int = 50):  # noqa: ARG002
        return FixedIncomeSignalsResponse(
            count=1,
            signals=[
                FixedIncomeSignalResponse(
                    date=date(2026, 6, 15),
                    country="US",
                    signal_name="credit_stress",
                    value=5.25,
                    strength="moderate",
                    direction="risk_off",
                    interpretation="Credit spreads are elevated.",
                )
            ],
        )


def test_fixed_income_regime_requires_bearer_token() -> None:
    client = TestClient(app)
    response = client.get(f"{PREFIX}/regime")
    assert response.status_code == 401


def test_fixed_income_regime_forbidden_without_market_scope() -> None:
    app.dependency_overrides[get_fixed_income_service] = lambda: _FakeFixedIncomeService()
    client = TestClient(app)
    token = _make_user_token(scopes=["advisor:read"])
    response = client.get(f"{PREFIX}/regime", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_fixed_income_regime_ok() -> None:
    app.dependency_overrides[get_fixed_income_service] = lambda: _FakeFixedIncomeService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{PREFIX}/regime", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest"]["bond_environment_label"] == "equity_hostile"
    assert payload["signals"][0]["signal_name"] == "curve_inversion"
    assert payload["etf_proxies"][0]["symbol"] == "TLT"
    app.dependency_overrides.clear()


def test_fixed_income_regime_not_found_when_empty() -> None:
    app.dependency_overrides[get_fixed_income_service] = lambda: _FakeFixedIncomeService(
        regime_exists=False
    )
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{PREFIX}/regime", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_fixed_income_regime_omits_etf_proxies_when_prices_missing() -> None:
    app.dependency_overrides[get_fixed_income_service] = lambda: _FakeFixedIncomeService(
        include_proxies=False
    )
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{PREFIX}/regime", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["etf_proxies"] == []
    app.dependency_overrides.clear()


def test_fixed_income_history_ok() -> None:
    app.dependency_overrides[get_fixed_income_service] = lambda: _FakeFixedIncomeService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{PREFIX}/history?limit=5", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["metrics"][0]["bond_environment_score"] == 38
    app.dependency_overrides.clear()


def test_fixed_income_signals_ok() -> None:
    app.dependency_overrides[get_fixed_income_service] = lambda: _FakeFixedIncomeService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get(f"{PREFIX}/signals?limit=5", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["signals"][0]["signal_name"] == "credit_stress"
    app.dependency_overrides.clear()
