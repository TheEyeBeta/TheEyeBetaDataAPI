"""Tests for exact security-master symbol resolution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.services import get_market_data_service
from app.auth.scopes import SCOPE_SYMBOLS_READ
from app.core.config import settings
from app.domain.models import ResolvedSymbol
from app.main import app
from app.repositories.interfaces import MarketDataRepository
from app.repositories.sql_market_data import SQLMarketDataRepository
from app.services.market_data_service import MarketDataService


def _make_user_token(scopes: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "symbol-resolver-test-user",
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }
    return jwt.encode(
        payload, settings.user_jwt_secret, algorithm=settings.user_jwt_algorithm
    )


def _resolved_symbol(
    *,
    instrument_id: int = 123,
    exchange: str = "NASDAQ",
    active: bool = True,
) -> ResolvedSymbol:
    return ResolvedSymbol(
        instrument_id=instrument_id,
        name="Apple Inc.",
        exchange=exchange,
        currency="USD",
        isin=None,
        cusip=None,
        figi=None,
        asset_class="equity",
        active=active,
    )


class _FakeMarketDataRepository:
    def __init__(self, matches: list[ResolvedSymbol]) -> None:
        self.matches = matches
        self.requested_symbols: list[str] = []

    def resolve_symbol(self, symbol: str) -> list[ResolvedSymbol]:
        self.requested_symbols.append(symbol)
        return self.matches


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _client_with_matches(
    matches: list[ResolvedSymbol],
) -> tuple[TestClient, _FakeMarketDataRepository]:
    repository = _FakeMarketDataRepository(matches)
    service = MarketDataService(cast(MarketDataRepository, repository))
    app.dependency_overrides[get_market_data_service] = lambda: service
    return TestClient(app), repository


def test_resolve_symbol_returns_exact_security_master_shape() -> None:
    client, repository = _client_with_matches([_resolved_symbol()])
    token = _make_user_token([SCOPE_SYMBOLS_READ])

    response = client.get(
        "/api/v1/symbols/resolve?symbol=%20aapl%20",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert repository.requested_symbols == ["AAPL"]
    assert response.json() == {
        "instrument_id": 123,
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isin": None,
        "cusip": None,
        "figi": None,
        "asset_class": "equity",
        "active": True,
    }


def test_resolve_symbol_returns_not_found_for_no_exact_match() -> None:
    client, _repository = _client_with_matches([])
    token = _make_user_token([SCOPE_SYMBOLS_READ])

    response = client.get(
        "/api/v1/symbols/resolve?symbol=missing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_resolve_symbol_rejects_cross_exchange_ambiguity() -> None:
    client, _repository = _client_with_matches(
        [
            _resolved_symbol(instrument_id=123, exchange="NASDAQ"),
            _resolved_symbol(instrument_id=456, exchange="NYSE", active=False),
        ]
    )
    token = _make_user_token([SCOPE_SYMBOLS_READ])

    response = client.get(
        "/api/v1/symbols/resolve?symbol=AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert (
        response.json()["error"]["message"]
        == "Symbol is ambiguous across exchanges: AAPL"
    )


def test_resolve_symbol_rejects_whitespace_only_symbol() -> None:
    client, repository = _client_with_matches([_resolved_symbol()])
    token = _make_user_token([SCOPE_SYMBOLS_READ])

    response = client.get(
        "/api/v1/symbols/resolve?symbol=%20%20",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert repository.requested_symbols == []


def test_resolve_symbol_requires_symbols_read_scope() -> None:
    client, _repository = _client_with_matches([_resolved_symbol()])
    token = _make_user_token(["market:read"])

    response = client.get(
        "/api/v1/symbols/resolve?symbol=AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_resolve_symbol_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/symbols/resolve?symbol=AAPL")

    assert response.status_code == 401


def test_sql_repository_reads_all_exact_matches_for_ambiguity_detection() -> None:
    session = MagicMock(spec=Session)
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "instrument_id": 123,
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "currency": "USD",
            "isin": None,
            "cusip": "037833100",
            "figi": None,
            "asset_class": "equity",
            "active": True,
        }
    ]
    repository = SQLMarketDataRepository(session)

    matches = repository.resolve_symbol("AAPL")

    assert matches == [
        ResolvedSymbol(
            instrument_id=123,
            name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            isin=None,
            cusip="037833100",
            figi=None,
            asset_class="equity",
            active=True,
        )
    ]
    statement, parameters = session.execute.call_args.args
    assert parameters == {"symbol": "AAPL"}
    assert "WHERE UPPER(i.symbol) = UPPER(:symbol)" in str(statement)
    assert "LIMIT 2" in str(statement)
