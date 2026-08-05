"""Auth endpoints for service principals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.api.dependencies.services import get_session
from app.auth.service_clients import get_service_client, validate_requested_scopes, verify_service_client_secret
from app.auth.scopes import LENS_DELEGATED_READ_SCOPES, SCOPE_LENS_DELEGATE, has_required_scopes
from app.auth.tokens import create_delegated_access_token, create_service_access_token, decode_user_token
from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.domain.errors import AuthenticationError
from app.schemas.auth import DelegatedTokenRequest, DelegatedTokenResponse, ServiceTokenRequest, ServiceTokenResponse
from app.policy.repository import PolicyRepository
from app.domain.errors import AuthorizationError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
security = HTTPBasic(auto_error=False)


@router.post("/service-token", response_model=ServiceTokenResponse)
def issue_service_token(
    request_body: ServiceTokenRequest,
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
    session: Session = Depends(get_session),
) -> ServiceTokenResponse:
    """Issue service JWT using client credentials."""
    if credentials is None:
        raise AuthenticationError("Missing service credentials")

    client = get_service_client(credentials.username, session=session)
    verify_service_client_secret(
        client,
        credentials.password,
        session=session,
        client_ip=get_client_ip(request),
    )
    granted_scopes = validate_requested_scopes(client, request_body.requested_scopes)

    token = create_service_access_token(
        subject=f"service:{client.client_id}",
        client_id=client.client_id,
        scopes=granted_scopes,
        expires_minutes=settings.service_token_expires_minutes,
    )
    return ServiceTokenResponse(
        access_token=token,
        expires_minutes=settings.service_token_expires_minutes,
        scopes=granted_scopes,
    )


@router.post("/delegated-token", response_model=DelegatedTokenResponse)
def issue_delegated_token(
    request_body: DelegatedTokenRequest,
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
    session: Session = Depends(get_session),
) -> DelegatedTokenResponse:
    """Exchange a verified Lens user token for a tenant-bound DataAPI token."""
    if credentials is None:
        raise AuthenticationError("Missing Lens service credentials")
    client = get_service_client(credentials.username, session=session)
    verify_service_client_secret(client, credentials.password, session=session, client_ip=get_client_ip(request))
    if not has_required_scopes(client.scopes, [SCOPE_LENS_DELEGATE]):
        raise AuthorizationError("Service client cannot delegate Lens users")
    user_principal = decode_user_token(request_body.subject_token)
    if user_principal is None:
        raise AuthenticationError("Invalid Lens user token")
    grant = PolicyRepository(session).grant_lens_delegation(
        client_id=client.client_id,
        subject=user_principal.subject,
    )
    granted_scopes = sorted(set(client.scopes).intersection(LENS_DELEGATED_READ_SCOPES))
    if not granted_scopes:
        raise AuthorizationError("Lens client has no delegable read scope")
    token = create_delegated_access_token(
        subject=user_principal.subject,
        actor_client_id=client.client_id,
        tenant_id=grant.tenant_id,
        product="LENS",
        scopes=granted_scopes,
        policy_version=grant.policy_version,
    )
    return DelegatedTokenResponse(
        access_token=token,
        expires_minutes=settings.delegated_token_expires_minutes,
        scopes=granted_scopes,
        tenant_id=grant.tenant_id,
    )
