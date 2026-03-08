"""FastAPI dependencies for authN/authZ."""

from __future__ import annotations

from fastapi import Depends, Header, Request

from app.auth.models import Principal, PrincipalType
from app.auth.service_clients import get_service_client, validate_mtls_subject
from app.auth.scopes import has_required_scopes
from app.auth.tokens import decode_access_token
from app.core.config import settings
from app.domain.errors import AuthenticationError, AuthorizationError


def _principal_from_mtls_headers(request: Request) -> Principal | None:
    if not settings.service_mtls_enabled:
        return None

    client_id = request.headers.get(settings.service_mtls_header_client_id)
    cert_subject = request.headers.get(settings.service_mtls_header_subject)
    if not client_id and not cert_subject:
        return None
    if not client_id or not cert_subject:
        raise AuthenticationError("Incomplete mTLS authentication headers")

    client = get_service_client(client_id.strip())
    validate_mtls_subject(client, cert_subject)
    return Principal(
        subject=f"service:{client.client_id}",
        principal_type=PrincipalType.SERVICE,
        scopes=frozenset(client.scopes),
        client_id=client.client_id,
    )


def get_principal(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    """Resolve bearer token to a normalized principal."""
    mtls_principal = _principal_from_mtls_headers(request)
    if mtls_principal:
        request.state.auth_type = "service-mtls"
        request.state.auth_subject = mtls_principal.subject
        return mtls_principal

    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Missing bearer token")
    principal = decode_access_token(token)
    request.state.auth_type = principal.principal_type.value
    request.state.auth_subject = principal.subject
    return principal


def require_scopes(required: list[str]):
    """Return dependency enforcing the provided scopes."""

    def _enforce(principal: Principal = Depends(get_principal)) -> Principal:
        if not has_required_scopes(principal.scopes, required):
            raise AuthorizationError("Insufficient scopes")
        return principal

    return _enforce
