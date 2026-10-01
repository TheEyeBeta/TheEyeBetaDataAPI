"""Tests for consistent error response shapes — 401, 403, 422."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


def _make_user_token(scopes: list[str]) -> str:
    import jwt

    from app.core.config import settings

    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "err-test-user",
            "scope": " ".join(scopes),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
        },
        settings.user_jwt_secret,
        algorithm=settings.user_jwt_algorithm,
    )


# ---------------------------------------------------------------------------
# 401 — no credentials
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/v1/context",
    "/api/v1/market-data/quotes?symbols=AAPL",
])
def test_unauthenticated_request_returns_401(path: str) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get(path)
    assert resp.status_code == 401
    body = resp.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]


def test_malformed_bearer_token_returns_401() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get(
        "/api/v1/context",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"


# ---------------------------------------------------------------------------
# 403 — wrong scope
# ---------------------------------------------------------------------------

def test_wrong_scope_returns_403() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    token = _make_user_token(scopes=["market:read"])
    client = TestClient(app)
    resp = client.get(
        "/api/v1/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# 422 — invalid parameters
# ---------------------------------------------------------------------------

def test_out_of_range_limit_returns_422() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    token = _make_user_token(scopes=["admin:read"])
    client = TestClient(app)
    resp = client.get(
        "/api/v1/admin/audit-events?limit=9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_422_message_does_not_leak_server_paths() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    token = _make_user_token(scopes=["admin:read"])
    client = TestClient(app)
    resp = client.get(
        "/api/v1/admin/audit-events?limit=9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "REQUEST_VALIDATION_ERROR"
    # Contract consumers (Lens, Admin) have always received the repr of the error list.
    assert error["message"].startswith("[{'type': 'less_than_equal'")
    assert "File " not in error["message"]
    assert ".py" not in error["message"]


# ---------------------------------------------------------------------------
# Request-ID propagation
# ---------------------------------------------------------------------------

def test_401_response_echoes_request_id() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get(
        "/api/v1/context",
        headers={"X-Request-ID": "test-req-abc123"},
    )
    assert resp.headers.get("x-request-id") == "test-req-abc123"


def test_401_includes_request_id_header_when_not_provided() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/context")
    header_keys = {k.lower() for k in resp.headers}
    assert "x-request-id" in header_keys


def test_422_does_not_echo_submitted_values() -> None:
    """A malformed body must not be reflected back (it may hold a secret)."""
    from fastapi.testclient import TestClient

    from app.main import app

    secret_like = "refresh-SECRET-VALUE-0123456789"
    resp = TestClient(app).post(
        "/api/v1/auth/refresh", json={"refresh_token": secret_like, "unexpected": secret_like}
    )
    assert resp.status_code == 422
    message = resp.json()["error"]["message"]
    assert "extra_forbidden" in message
    assert secret_like not in message
    assert "'input'" not in message and "'ctx'" not in message and "'url'" not in message


def test_named_query_db_failure_does_not_return_driver_text() -> None:
    from sqlalchemy.exc import ProgrammingError

    from app.domain.errors import DatabaseUnavailableError
    from app.repositories.sql_market_data import SQLMarketDataRepository

    class _Session:
        def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            raise ProgrammingError("SELECT secret_column FROM theeyebeta.x", {"limit": 5}, Exception("boom"))

    repo = SQLMarketDataRepository(_Session())  # type: ignore[arg-type]
    with pytest.raises(DatabaseUnavailableError) as raised:
        repo.execute_named_query("orders", limit=5)
    assert "SELECT" not in raised.value.message
    assert "secret_column" not in raised.value.message
