"""Authentication dependencies."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Header, HTTPException, Request, status
from jwt import InvalidTokenError

from app.core.config import settings


@dataclass
class AuthContext:
    """Authenticated principal context."""

    subject: str
    auth_type: str


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require a valid X-API-Key header for protected routes."""
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def create_access_token(subject: str, expires_minutes: int = 60) -> str:
    """Create a signed JWT for service-to-service authentication."""
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_jwt(token: str) -> dict:
    """Decode and validate JWT token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def require_auth(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AuthContext:
    """Authorize requests using either API key or Bearer JWT."""
    # API key path
    if x_api_key and hmac.compare_digest(x_api_key, settings.api_key):
        auth = AuthContext(subject="api-key-client", auth_type="api_key")
        request.state.auth_subject = auth.subject
        request.state.auth_type = auth.auth_type
        return auth

    # JWT Bearer path
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = _decode_jwt(token)
            subject = str(claims.get("sub", "jwt-client"))
            auth = AuthContext(subject=subject, auth_type="jwt")
            request.state.auth_subject = auth.subject
            request.state.auth_type = auth.auth_type
            return auth
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication. Provide X-API-Key or Authorization: Bearer <token>",
    )
