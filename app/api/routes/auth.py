"""Auth endpoints for service principals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.api.dependencies.services import get_session
from app.auth.service_clients import get_service_client, validate_requested_scopes, verify_service_client_secret
from app.auth.tokens import create_service_access_token
from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.domain.errors import AuthenticationError
from app.schemas.auth import ServiceTokenRequest, ServiceTokenResponse

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
