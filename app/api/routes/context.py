"""Context routes for constrained DB-backed AI context."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_advisor_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ADVISOR_READ
from app.schemas.context import AdvisorContextResponse
from app.services.advisor_service import AdvisorService

router = APIRouter(tags=["advisor"])


@router.get("/api/v1/context", response_model=AdvisorContextResponse)
@router.get("/api/v1/advisor/context", response_model=AdvisorContextResponse)
def get_context(
    ticker: str | None = Query(default=None, description="Optional ticker for focused context"),
    ticker_limit: int = Query(default=25, ge=1, le=200),
    news_limit: int = Query(default=10, ge=1, le=50),
    _=Depends(require_scopes([SCOPE_ADVISOR_READ])),
    advisor_service: AdvisorService = Depends(get_advisor_service),
) -> AdvisorContextResponse:
    """Get safe context payload for an external AI client."""
    return advisor_service.get_context(ticker=ticker, ticker_limit=ticker_limit, news_limit=news_limit)
