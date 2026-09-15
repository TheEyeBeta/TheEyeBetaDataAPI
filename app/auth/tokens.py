"""Token creation and validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
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


def _decode_options(*, require_iss_aud: bool) -> dict[str, Any]:
    """Build PyJWT options: always require exp+iat; iss/aud gated by flag.

    When iss/aud are not required, explicitly disable verification so tokens that
    *do* carry those claims (current issuers) still validate without an
    audience= / issuer= argument.
    """
    required = ["exp", "iat"]
    if require_iss_aud:
        required.extend(["iss", "aud"])
    return {
        "require": required,
        "verify_iss": require_iss_aud,
        "verify_aud": require_iss_aud,
    }


def decode_signed_claims(
    token: str,
    *,
    key: Any | None = None,
    keys: list[Any] | None = None,
    algorithms: list[str],
    issuer: str | None = None,
    audience: str | None = None,
    require_iss_aud: bool | None = None,
) -> dict[str, Any]:
    """Decode a JWT with an explicit algorithm allowlist and claim requirements.

    Pass either ``key`` (single) or ``keys`` (ordered verify list: current then
    previous). ``algorithms`` must be a non-empty allowlist.
    """
    if not algorithms:
        raise AuthenticationError("JWT algorithm allowlist is empty")

    candidates: list[Any]
    if keys is not None:
        candidates = [k for k in keys if k is not None and k != ""]
    elif key is not None and key != "":
        candidates = [key]
    else:
        raise AuthenticationError("JWT verification key not configured")
    if not candidates:
        raise AuthenticationError("JWT verification key not configured")

    enforce_iss_aud = (
        settings.jwt_require_iss_aud if require_iss_aud is None else require_iss_aud
    )
    options = _decode_options(require_iss_aud=enforce_iss_aud)
    kwargs: dict[str, Any] = {
        "algorithms": algorithms,
        "options": options,
    }
    if enforce_iss_aud:
        if not issuer or not audience:
            raise AuthenticationError("JWT issuer/audience not configured")
        kwargs["issuer"] = issuer
        kwargs["audience"] = audience

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return jwt.decode(token, candidate, **kwargs)
        except InvalidTokenError as exc:
            last_error = exc
            continue
    raise AuthenticationError("Invalid bearer token") from last_error


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
    return jwt.encode(
        payload,
        settings.effective_jwt_signing_secret,
        algorithm=settings.jwt_algorithm,
    )


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
    return jwt.encode(
        payload,
        settings.effective_jwt_signing_secret,
        algorithm=settings.jwt_algorithm,
    )


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
            claims = decode_signed_claims(
                token,
                key=signing_key,
                algorithms=settings.parsed_user_jwt_algorithms or [settings.user_jwt_algorithm],
                issuer=settings.user_jwt_issuer or settings.jwt_issuer,
                audience=settings.user_jwt_audience or settings.jwt_audience,
            )
        except (AuthenticationError, PyJWKClientError):
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
        claims = decode_signed_claims(
            token,
            keys=settings.user_jwt_verify_secrets,
            algorithms=[settings.user_jwt_algorithm],
            issuer=settings.user_jwt_issuer or settings.jwt_issuer,
            audience=settings.user_jwt_audience or settings.jwt_audience,
        )
    except AuthenticationError:
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
        claims = decode_signed_claims(
            token,
            keys=settings.jwt_verify_secrets,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except AuthenticationError:
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
        claims = decode_signed_claims(
            token,
            keys=settings.jwt_verify_secrets,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except AuthenticationError:
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
