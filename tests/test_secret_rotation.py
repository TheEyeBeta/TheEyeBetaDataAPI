"""Phase 2: zero-downtime JWT signing-secret rotation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.tokens import create_service_access_token, decode_access_token, decode_user_token
from app.core.config import settings
from app.domain.errors import AuthenticationError


def test_token_signed_with_previous_secret_validates_while_previous_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = "previous-jwt-signing-secret-24c-min!!"
    current = "current-jwt-signing-secret-24c-min!!!"
    monkeypatch.setattr(settings, "jwt_secret", current)
    monkeypatch.setattr(settings, "jwt_signing_secret_current", current)
    monkeypatch.setattr(settings, "jwt_signing_secret_previous", previous)

    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "sub": "service:vi-app",
            "client_id": "vi-app",
            "token_use": "service",
            "scope": "market:read",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        previous,
        algorithm=settings.jwt_algorithm,
    )
    principal = decode_access_token(legacy)
    assert principal.client_id == "vi-app"

    # New tokens sign with CURRENT only.
    fresh = create_service_access_token("service:vi-app", "vi-app", ["market:read"], 30)
    header_payload = jwt.get_unverified_header(fresh)
    assert header_payload["alg"] == settings.jwt_algorithm
    # Decode with current key succeeds; previous-only would fail.
    jwt.decode(
        fresh,
        current,
        algorithms=[settings.jwt_algorithm],
        options={"verify_aud": False, "verify_iss": False, "require": ["exp", "iat"]},
    )
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            fresh,
            previous,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False, "verify_iss": False, "require": ["exp", "iat"]},
        )


def test_token_signed_with_previous_secret_fails_once_previous_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = "previous-jwt-signing-secret-24c-min!!"
    current = "current-jwt-signing-secret-24c-min!!!"
    monkeypatch.setattr(settings, "jwt_secret", current)
    monkeypatch.setattr(settings, "jwt_signing_secret_current", current)
    monkeypatch.setattr(settings, "jwt_signing_secret_previous", previous)

    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "sub": "service:vi-app",
            "client_id": "vi-app",
            "token_use": "service",
            "scope": "market:read",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        previous,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(legacy).client_id == "vi-app"

    monkeypatch.setattr(settings, "jwt_signing_secret_previous", None)
    with pytest.raises(AuthenticationError):
        decode_access_token(legacy)


def test_user_jwt_previous_secret_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = "previous-user-jwt-secret-24chars!!"
    current = "current-user-jwt-secret-24chars!!!"
    monkeypatch.setattr(settings, "user_jwt_secret", current)
    monkeypatch.setattr(settings, "user_jwt_secret_previous", previous)
    monkeypatch.setattr(settings, "user_jwt_jwks_url", None)

    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "sub": "user-1",
            "scope": "market:read",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        previous,
        algorithm=settings.user_jwt_algorithm,
    )
    principal = decode_user_token(legacy)
    assert principal is not None
    assert principal.subject == "user-1"

    monkeypatch.setattr(settings, "user_jwt_secret_previous", None)
    assert decode_user_token(legacy) is None
