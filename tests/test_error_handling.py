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
