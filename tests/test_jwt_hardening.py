"""Phase 1 JWT / FastAPI auth hardening regression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.tokens import create_service_access_token, decode_access_token, decode_signed_claims
from app.core.config import Settings, openapi_route_kwargs, settings
from app.domain.errors import AuthenticationError
from app.main import app
from app.schemas.accounts import CreateAccountRequest, DeleteAccountRequest
from app.schemas.auth import DelegatedTokenRequest, ServiceTokenRequest


def _now_claims(**extra: object) -> dict:
    now = datetime.now(UTC)
    payload = {
        "sub": "service:vi-app",
        "client_id": "vi-app",
        "token_use": "service",
        "scope": "market:read",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    payload.update(extra)
    return payload


def test_alg_none_token_is_rejected_with_401() -> None:
    payload = _now_claims()
    # Unsigned "none" algorithm — must never authenticate.
    forged = jwt.encode(payload, key="", algorithm="none")
    client = TestClient(app)
    response = client.get(
        "/api/v1/market-data/quotes?symbols=AAPL",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_unexpected_algorithm_is_rejected() -> None:
    payload = _now_claims()
    # Signed with HS256 but presented to a path that only allows a different alg.
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_signed_claims(
            token,
            key=settings.jwt_secret,
            algorithms=["HS384"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            require_iss_aud=True,
        )


def test_missing_iat_is_rejected() -> None:
    payload = _now_claims()
    del payload["iat"]
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(AuthenticationError):
        decode_signed_claims(
            token,
            key=settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            require_iss_aud=False,
        )


def test_missing_iss_aud_allowed_when_grace_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_require_iss_aud", False)
    payload = _now_claims()
    del payload["iss"]
    del payload["aud"]
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    claims = decode_signed_claims(
        token,
        key=settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        require_iss_aud=False,
    )
    assert claims["sub"] == "service:vi-app"


def test_missing_iss_aud_rejected_when_grace_flag_true() -> None:
    payload = _now_claims()
    del payload["iss"]
    del payload["aud"]
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(AuthenticationError):
        decode_signed_claims(
            token,
            key=settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            require_iss_aud=True,
        )


def test_issued_service_token_still_decodes() -> None:
    token = create_service_access_token(
        subject="service:vi-app",
        client_id="vi-app",
        scopes=["market:read"],
        expires_minutes=30,
    )
    principal = decode_access_token(token)
    assert principal.client_id == "vi-app"
    assert "market:read" in principal.scopes


@pytest.mark.parametrize(
    "model,payload",
    [
        (ServiceTokenRequest, {"requested_scopes": ["market:read"], "extra_field": True}),
        (DelegatedTokenRequest, {"subject_token": "x" * 24, "nonce": "nope"}),
        (
            CreateAccountRequest,
            {"email": "user@example.com", "plan": "free", "role": "admin"},
        ),
        (DeleteAccountRequest, {"approval_code": "secret", "debug": 1}),
    ],
)
def test_auth_request_models_forbid_extra_fields(model: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_service_token_endpoint_rejects_unknown_body_fields() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/service-token",
        auth=("vi-app", "vi-app-secret-which-is-24chars!!"),
        json={"requested_scopes": ["market:read"], "admin": True},
    )
    assert response.status_code == 422


def test_cors_never_allows_wildcard_with_credentials() -> None:
    # Runtime middleware guard + production settings validator.
    assert "*" not in settings.parsed_cors_origins
    with pytest.raises(ValidationError):
        Settings(
            database_url=settings.database_url,
            jwt_secret=settings.jwt_secret,
            environment="production",
            cors_origins="*",
            trusted_hosts="dataapiprod.theeyebeta.store",
            policy_enforcement_enabled=True,
            service_client_auth_mode="environment",
            service_clients_json=settings.service_clients_json,
        )


def test_openapi_disabled_in_production() -> None:
    urls = openapi_route_kwargs("production")
    assert urls["docs_url"] is None
    assert urls["redoc_url"] is None
    assert urls["openapi_url"] is None
    # Development/test app still exposes docs (ENVIRONMENT=development in conftest).
    assert openapi_route_kwargs("development")["docs_url"] == "/docs"
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 200


def _settings(**overrides) -> Settings:
    base = {
        "database_url": settings.database_url,
        "jwt_secret": settings.jwt_secret,
        "trusted_hosts": "dataapiprod.theeyebeta.store",
        "policy_enforcement_enabled": True,
        "service_client_auth_mode": "environment",
        "service_clients_json": settings.service_clients_json,
    }
    base.update(overrides)
    return Settings(**base)


def test_jwt_secrets_must_be_at_least_32_bytes() -> None:
    with pytest.raises(ValidationError):
        _settings(jwt_secret="x" * 31)
    with pytest.raises(ValidationError):
        _settings(jwt_signing_secret_current="y" * 31)
    with pytest.raises(ValidationError):
        _settings(user_jwt_secret="z" * 31)
    assert _settings(jwt_secret="x" * 32).jwt_secret == "x" * 32


def test_production_cors_always_admits_admin_frontend_origins() -> None:
    prod = _settings(environment="production", cors_origins="")
    assert "https://admin.theeyebeta.store" in prod.parsed_cors_origins
    assert "tauri://localhost" in prod.parsed_cors_origins


def test_non_production_cors_is_exactly_the_configured_list() -> None:
    dev = _settings(environment="development", cors_origins="http://localhost:5173")
    assert dev.parsed_cors_origins == ["http://localhost:5173"]


# ---------------------------------------------------------------------------
# JWT_REQUIRE_ISS_AUD=true is the default (docs/IAM_CONSUMER_INVENTORY.md §2).
# Every production consumer (Lens, Lens admin route, Prod admin-service,
# TheEyeBetaLocal) obtains its token from /api/v1/auth/service-token and sends
# it back unchanged, and DataAPI has put iss/aud in every token it mints since
# 2026-03. These tests pin that compatibility.
# ---------------------------------------------------------------------------


def test_iss_aud_enforced_by_default() -> None:
    assert Settings.model_fields["jwt_require_iss_aud"].default is True
    assert settings.jwt_require_iss_aud is True  # tests run the production default


def _quotes(token: str) -> int:
    return (
        TestClient(app)
        .get("/api/v1/market-data/quotes?symbols=AAPL", headers={"Authorization": f"Bearer {token}"})
        .status_code
    )


def _sign(payload: dict) -> str:
    return jwt.encode(payload, settings.jwt_verify_secrets[0], algorithm=settings.jwt_algorithm)


def test_minted_service_token_is_accepted_under_enforcement() -> None:
    token = create_service_access_token("service:vi-app", "vi-app", ["market:read"], 5)
    principal = decode_access_token(token)
    assert principal.client_id == "vi-app"


@pytest.mark.parametrize("missing", ["iss", "aud"])
def test_token_without_iss_or_aud_is_401_under_enforcement(missing: str) -> None:
    payload = _now_claims()
    del payload[missing]
    assert _quotes(_sign(payload)) == 401


@pytest.mark.parametrize(("claim", "value"), [("iss", "someone-else"), ("aud", "other-audience")])
def test_token_for_another_issuer_or_audience_is_401(claim: str, value: str) -> None:
    assert _quotes(_sign(_now_claims(**{claim: value}))) == 401
