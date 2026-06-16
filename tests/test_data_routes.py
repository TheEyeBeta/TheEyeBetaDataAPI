"""Tests for generic read-only theeyebeta table routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_readonly_data_repository
from app.core.config import settings
from app.domain.errors import ValidationAppError
from app.main import app
from app.repositories.sql_data import SQLReadOnlyDataRepository
from app.schemas.data import DataColumnInfo, DataTableInfo


class _FakeDataRepository:
    def list_tables(self) -> list[DataTableInfo]:
        return [
            DataTableInfo(name="instruments", table_type="BASE TABLE", row_count_estimate=10),
            DataTableInfo(name="admin_users", table_type="BASE TABLE", row_count_estimate=2),
        ]

    def list_columns(self, table: str) -> list[DataColumnInfo]:
        if table == "instruments":
            return [
                DataColumnInfo(name="id", data_type="bigint", nullable=False, ordinal_position=1),
                DataColumnInfo(name="symbol", data_type="text", nullable=False, ordinal_position=2),
            ]
        return [DataColumnInfo(name="id", data_type="bigint", nullable=False, ordinal_position=1)]

    def query_rows(self, **kwargs):  # noqa: ANN003
        table = str(kwargs["table"])
        return [{"id": 1, "symbol": "AAPL"}] if table == "instruments" else [{"id": 1}]


def _make_user_token(scopes: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "user-data",
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }
    return jwt.encode(payload, settings.user_jwt_secret, algorithm=settings.user_jwt_algorithm)


def test_non_admin_lists_only_basic_tables() -> None:
    app.dependency_overrides[get_readonly_data_repository] = lambda: _FakeDataRepository()
    client = TestClient(app)
    token = _make_user_token(["market:read"])

    response = client.get("/api/v1/data/tables", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert [table["name"] for table in response.json()["tables"]] == ["instruments"]
    app.dependency_overrides.clear()


def test_non_admin_cannot_read_admin_table() -> None:
    app.dependency_overrides[get_readonly_data_repository] = lambda: _FakeDataRepository()
    client = TestClient(app)
    token = _make_user_token(["market:read"])

    response = client.get("/api/v1/data/tables/admin_users/rows", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_admin_can_read_any_theeyebeta_table() -> None:
    app.dependency_overrides[get_readonly_data_repository] = lambda: _FakeDataRepository()
    client = TestClient(app)
    token = _make_user_token(["admin:read"])

    response = client.get("/api/v1/data/tables/admin_users/rows", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["rows"] == [{"id": 1}]
    app.dependency_overrides.clear()


def test_table_api_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/data/tables")
    assert response.status_code == 401


def test_filter_parser_rejects_unknown_column() -> None:
    with pytest.raises(ValidationAppError):
        SQLReadOnlyDataRepository._parse_filter("ticker:eq:AAPL", {"symbol"})


def test_filter_parser_accepts_safe_filter() -> None:
    assert SQLReadOnlyDataRepository._parse_filter("symbol:eq:AAPL", {"symbol"}) == ("symbol", "eq", "AAPL")
