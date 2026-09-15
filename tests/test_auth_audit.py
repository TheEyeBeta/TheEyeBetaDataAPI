"""Phase 4 auth audit + least-privilege provisioning helpers."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_scope_failure_writes_auth_audit(monkeypatch) -> None:
    calls: list[dict] = []

    def _capture(**kwargs):  # noqa: ANN003
        calls.append(kwargs)

    monkeypatch.setattr("app.auth.audit.record_auth_audit", _capture)

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "user-audit",
            "scope": "market:read",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
        },
        settings.user_jwt_secret,
        algorithm=settings.user_jwt_algorithm,
    )
    client = TestClient(app)
    response = client.get("/api/v1/context", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert calls, "expected auth audit write on 403"
    assert calls[0]["outcome"] == "forbidden"
    assert "advisor:read" in (calls[0]["scope_required"] or "")


def test_least_privilege_helper_requires_explicit_scopes() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "provision_db_service_client.py"
    spec = importlib.util.spec_from_file_location("provision_db_service_client", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    session = MagicMock()
    try:
        module._apply_least_privilege_scopes(
            session, "00000000-0000-0000-0000-000000000001", [], "tester"
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "least-privilege" in str(exc).lower()
