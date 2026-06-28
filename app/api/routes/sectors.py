"""Sector aggregate routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_MARKET_READ
from app.schemas.market import SectorDailyResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/sectors", tags=["sectors"])


@router.get("/daily", response_model=SectorDailyResponse)
def get_sector_daily(
    sector: str | None = Query(default=None, description="Filter to one sector name"),
    limit: int = Query(default=252, ge=1, le=2000),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> SectorDailyResponse:
    return service.get_sector_daily(sector=sector, limit=limit)
