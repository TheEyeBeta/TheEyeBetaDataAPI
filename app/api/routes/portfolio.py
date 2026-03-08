"""Portfolio routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_portfolio_service
from app.auth.dependencies import require_scopes
from app.auth.models import Principal, PrincipalType
from app.auth.scopes import SCOPE_PORTFOLIO_READ
from app.domain.errors import AuthorizationError, ValidationAppError
from app.schemas.market import PortfolioStateResponse
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get("/state", response_model=PortfolioStateResponse)
def get_portfolio_state(
    owner_subject: str | None = Query(default=None, min_length=1, max_length=128),
    position_limit: int = Query(default=50, ge=1, le=500),
    principal: Principal = Depends(require_scopes([SCOPE_PORTFOLIO_READ])),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioStateResponse:
    """Ownership-aware portfolio state endpoint."""
    if principal.principal_type == PrincipalType.USER:
        if owner_subject and owner_subject != principal.subject:
            raise AuthorizationError("Users can only access their own portfolio state")
        effective_owner = principal.subject
    else:
        if not owner_subject:
            raise ValidationAppError("owner_subject is required for service principals")
        effective_owner = owner_subject
    return service.get_state(owner_subject=effective_owner, position_limit=position_limit)
