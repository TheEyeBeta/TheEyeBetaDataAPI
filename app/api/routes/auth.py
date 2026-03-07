"""Auth endpoints for issuing service JWTs."""

from fastapi import APIRouter, Depends

from app.core.security import create_access_token, require_api_key
from app.schemas.auth import TokenRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse, dependencies=[Depends(require_api_key)])
def issue_token(request: TokenRequest) -> TokenResponse:
    """Issue JWT token for machine-to-machine callers."""
    token = create_access_token(subject=request.subject, expires_minutes=request.expires_minutes)
    return TokenResponse(access_token=token, expires_minutes=request.expires_minutes)
