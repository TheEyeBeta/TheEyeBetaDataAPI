"""Service credential registry and validation."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from app.core.config import settings
from app.auth.scopes import has_required_scopes
from app.domain.errors import AuthenticationError, AuthorizationError


@dataclass(frozen=True)
class ServiceClient:
    """Configured service client identity."""

    client_id: str
    secret: str
    scopes: list[str]


def get_service_client(client_id: str) -> ServiceClient:
    raw = settings.parsed_service_clients.get(client_id)
    if not raw:
        raise AuthenticationError("Unknown service client")
    scopes = raw.get("scopes")
    secret = str(raw.get("secret", ""))
    if not isinstance(scopes, list) or not secret:
        raise AuthenticationError("Invalid service client configuration")
    return ServiceClient(client_id=client_id, secret=secret, scopes=[str(scope) for scope in scopes])


def verify_service_client_secret(client: ServiceClient, provided_secret: str) -> None:
    if not provided_secret or not hmac.compare_digest(client.secret, provided_secret):
        raise AuthenticationError("Invalid service credentials")


def validate_requested_scopes(client: ServiceClient, requested_scopes: list[str]) -> list[str]:
    """Ensure requested scopes are subset of client-assigned scopes."""
    if not requested_scopes:
        return client.scopes
    if not has_required_scopes(client.scopes, requested_scopes):
        raise AuthorizationError("Requested scopes exceed service client grants")
    return requested_scopes


def validate_mtls_subject(client: ServiceClient, subject: str) -> None:
    """Validate that certificate subject matches configured service allowlist."""
    if not settings.service_mtls_enabled:
        raise AuthenticationError("mTLS authentication is not enabled")
    normalized_subject = subject.strip()
    if not normalized_subject:
        raise AuthenticationError("Missing certificate subject")

    allowed_subjects = settings.parsed_service_mtls_subjects.get(client.client_id, [])
    if not allowed_subjects:
        raise AuthenticationError("No mTLS subject allowlist configured for service client")
    if not any(hmac.compare_digest(allowed, normalized_subject) for allowed in allowed_subjects):
        raise AuthenticationError("Certificate subject is not allowed for this service client")
