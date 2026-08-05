"""Token creation and validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError

from app.auth.models import Principal, PrincipalType
from app.core.config import settings
from app.domain.errors import AuthenticationError

_jwks_client: PyJWKClient | None = None


def _parse_scopes(claims: dict) -> frozenset[str]:
    scopes = claims.get("scopes")
    if isinstance(scopes, list):
        return frozenset(str(scope).strip() for scope in scopes if str(scope).strip())
    scope_string = claims.get("scope", "")
    if isinstance(scope_string, str):
        return frozenset(part.strip() for part in scope_string.split(" ") if part.strip())
    return frozenset()


def create_service_access_token(subject: str, client_id: str, scopes: list[str], expires_minutes: int) -> str:
    """Create an internal service JWT."""
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "client_id": client_id,
        "token_use": "service",
        "scope": " ".join(scopes),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_delegated_access_token(
    *,
    subject: str,
    actor_client_id: str,
    tenant_id: str,
    product: str,
    scopes: list[str],
    policy_version: int,
) -> str:
    """Create a short-lived DataAPI token bound to a Lens user and backend."""
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "act": {"sub": f"service:{actor_client_id}"},
        "client_id": actor_client_id,
        "tenant_id": tenant_id,
        "product": product,
        "policy_version": policy_version,
        "token_use": "delegated",
        "scope": " ".join(scopes),
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.delegated_token_expires_minutes)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if not settings.user_jwt_jwks_url:
        raise AuthenticationError("JWKS URL not configured")
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.user_jwt_jwks_url)
    return _jwks_client


def decode_user_token(token: str) -> Principal | None:
    if settings.user_jwt_jwks_url:
        try:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=settings.parsed_user_jwt_algorithms or [settings.user_jwt_algorithm],
                issuer=settings.user_jwt_issuer or settings.jwt_issuer,
                audience=settings.user_jwt_audience or settings.jwt_audience,
            )
        except (InvalidTokenError, PyJWKClientError):
            return None
        if claims.get("token_use") not in (None, "user"):
            return None
        subject = str(claims.get("sub", "")).strip()
        if not subject:
            raise AuthenticationError("User token missing sub claim")
        return Principal(
            subject=subject,
            principal_type=PrincipalType.USER,
            scopes=_parse_scopes(claims),
            client_id=None,
        )

    if not settings.user_jwt_secret:
        return None
    try:
        claims = jwt.decode(
            token,
            settings.user_jwt_secret,
            algorithms=[settings.user_jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except InvalidTokenError:
        return None
    if claims.get("token_use") not in (None, "user"):
        return None
    subject = str(claims.get("sub", "")).strip()
    if not subject:
        raise AuthenticationError("User token missing sub claim")
    return Principal(
        subject=subject,
        principal_type=PrincipalType.USER,
        scopes=_parse_scopes(claims),
        client_id=None,
    )


# Kept for existing tests and callers while the public name is adopted.
_decode_user_token = decode_user_token


def _decode_delegated_token(token: str) -> Principal | None:
    """Decode a DataAPI-issued delegated token before user-token fallbacks."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except InvalidTokenError:
        return None
    if claims.get("token_use") != "delegated":
        return None
    subject = str(claims.get("sub", "")).strip()
    client_id = str(claims.get("client_id", "")).strip()
    tenant_id = str(claims.get("tenant_id", "")).strip()
    product = str(claims.get("product", "")).strip()
    token_id = str(claims.get("jti", "")).strip()
    policy_version = claims.get("policy_version")
    if not all((subject, client_id, tenant_id, product, token_id)) or not isinstance(policy_version, int):
        raise AuthenticationError("Delegated token missing required claims")
    return Principal(
        subject=subject,
        principal_type=PrincipalType.USER,
        scopes=_parse_scopes(claims),
        client_id=client_id,
        tenant_id=tenant_id,
        product=product,
        token_id=token_id,
        policy_version=policy_version,
        delegated=True,
    )


def _decode_service_token(token: str) -> Principal | None:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except InvalidTokenError:
        return None
    if claims.get("token_use") != "service":
        return None
    subject = str(claims.get("sub", "")).strip()
    client_id = str(claims.get("client_id", "")).strip()
    if not subject or not client_id:
        raise AuthenticationError("Service token missing required claims")
    return Principal(
        subject=subject,
        principal_type=PrincipalType.SERVICE,
        scopes=_parse_scopes(claims),
        client_id=client_id,
    )


def decode_access_token(token: str) -> Principal:
    """Decode either service token or user token and return normalized principal."""
    service_principal = _decode_service_token(token)
    if service_principal:
        return service_principal

    delegated_principal = _decode_delegated_token(token)
    if delegated_principal:
        return delegated_principal

    user_principal = decode_user_token(token)
    if user_principal:
        return user_principal

    raise AuthenticationError("Invalid bearer token")
