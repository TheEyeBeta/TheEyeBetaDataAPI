"""Integration tests for scope enforcement rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_internal_service, get_portfolio_service
from app.core.config import settings
from app.main import app
from app.schemas.market import InternalJobResponse, PortfolioStateResponse


class _FakeInternalService:
    def enqueue_rebuild(self, **kwargs) -> InternalJobResponse:  # noqa: ANN003
        return InternalJobResponse(
            status="queued",
            command_id="cmd-1",
            command_type="rebuild_indicators",
            created_at=None,
        )


class _FakePortfolioService:
    def get_state(self, *, owner_subject: str, position_limit: int) -> PortfolioStateResponse:  # noqa: ARG002
        return PortfolioStateResponse(owner_subject=owner_subject, valuation=None, positions=[])


def _make_user_token(scopes: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "user-abc",
        "scope": " ".join(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=60)).timestamp()),
    }
    return jwt.encode(payload, settings.user_jwt_secret, algorithm=settings.user_jwt_algorithm)


def _issue_service_token(client: TestClient, username: str, password: str, scopes: list[str]) -> str:
    response = client.post(
        "/api/v1/auth/service-token",
        auth=(username, password),
        json={"requested_scopes": scopes},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_internal_job_requires_internal_jobs_scope() -> None:
    app.dependency_overrides[get_internal_service] = lambda: _FakeInternalService()
    client = TestClient(app)
    no_scope_token = _make_user_token(scopes=["advisor:read"])
    forbidden = client.post(
        "/api/v1/internal/jobs/rebuild-indicators",
        headers={"Authorization": f"Bearer {no_scope_token}"},
    )
    assert forbidden.status_code == 403

    allowed_token = _make_user_token(scopes=["internal:jobs"])
    allowed = client.post(
        "/api/v1/internal/jobs/rebuild-indicators",
        headers={"Authorization": f"Bearer {allowed_token}"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "queued"
    app.dependency_overrides.clear()


def test_portfolio_enforces_user_ownership() -> None:
    app.dependency_overrides[get_portfolio_service] = lambda: _FakePortfolioService()
    client = TestClient(app)
    token = _make_user_token(scopes=["portfolio:read"])

    own = client.get(
        "/api/v1/portfolio/state",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert own.status_code == 200
    assert own.json()["owner_subject"] == "user-abc"

    forbidden = client.get(
        "/api/v1/portfolio/state?owner_subject=another-user",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert forbidden.status_code == 403
    app.dependency_overrides.clear()


def test_portfolio_service_requires_owner_subject() -> None:
    app.dependency_overrides[get_portfolio_service] = lambda: _FakePortfolioService()
    client = TestClient(app)
    token = _issue_service_token(
        client,
        "trade-engine",
        "trade-engine-secret-which-is-24chars",
        ["portfolio:read"],
    )

    missing_owner = client.get(
        "/api/v1/portfolio/state",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing_owner.status_code == 422

    with_owner = client.get(
        "/api/v1/portfolio/state?owner_subject=user-abc",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert with_owner.status_code == 200
    assert with_owner.json()["owner_subject"] == "user-abc"
    app.dependency_overrides.clear()
