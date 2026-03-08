"""Tests for authn/authz and advisor routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_advisor_service
from app.core.config import settings
from app.main import app
from app.schemas.chat import ChatResponse
from app.schemas.context import AdvisorContextResponse, NewsItemResponse, TickerSummaryResponse


class _FakeAdvisorService:
    def get_context(self, ticker: str | None, ticker_limit: int, news_limit: int) -> AdvisorContextResponse:  # noqa: ARG002
        return AdvisorContextResponse(
            tickers=[TickerSummaryResponse(ticker="AAPL", company_name="Apple Inc.")],
            news=[NewsItemResponse(headline="Fed update")],
            ticker_snapshot=None,
        )

    def chat(self, question: str, ticker: str | None) -> ChatResponse:  # noqa: ARG002
        return ChatResponse(answer="Mock answer", used_ticker=ticker, context_rows=1)


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


def test_issue_service_token_requires_basic_credentials() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/auth/service-token", json={"requested_scopes": ["market:read"]})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_issue_service_token_with_basic_credentials_succeeds() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/service-token",
        auth=("vi-app", "vi-app-secret-which-is-24chars!!"),
        json={"requested_scopes": ["market:read", "advisor:read"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert set(payload["scopes"]) == {"market:read", "advisor:read"}
    assert isinstance(payload["access_token"], str) and payload["access_token"]


def test_context_requires_bearer_token() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/context")
    assert response.status_code == 401


def test_context_forbidden_without_required_scope() -> None:
    app.dependency_overrides[get_advisor_service] = lambda: _FakeAdvisorService()
    client = TestClient(app)
    token = _make_user_token(scopes=["market:read"])
    response = client.get("/api/v1/context", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    app.dependency_overrides.clear()


def test_context_allows_user_with_advisor_scope() -> None:
    app.dependency_overrides[get_advisor_service] = lambda: _FakeAdvisorService()
    client = TestClient(app)
    token = _make_user_token(scopes=["advisor:read"])
    response = client.get("/api/v1/context?ticker=AAPL", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"][0]["ticker"] == "AAPL"
    app.dependency_overrides.clear()


def test_chat_allows_user_with_advisor_scope() -> None:
    app.dependency_overrides[get_advisor_service] = lambda: _FakeAdvisorService()
    client = TestClient(app)
    token = _make_user_token(scopes=["advisor:read"])
    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What happened?", "ticker": "AAPL"},
    )
    assert response.status_code == 200
    assert response.json() == {"answer": "Mock answer", "used_ticker": "AAPL", "context_rows": 1}
    app.dependency_overrides.clear()
