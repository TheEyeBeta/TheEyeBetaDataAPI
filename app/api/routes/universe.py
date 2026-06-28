"""Universe cap-rank and cap-event routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_MARKET_READ
from app.schemas.market import CapEventsResponse, UniverseActiveResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/universe", tags=["universe"])


@router.get("/active", response_model=UniverseActiveResponse)
def get_universe_active(
    min_market_cap: float = Query(default=500_000_000, ge=0),
    limit: int = Query(default=200, ge=1, le=2000),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> UniverseActiveResponse:
    return service.get_universe_active(min_market_cap=min_market_cap, limit=limit)


@router.get("/cap-events", response_model=CapEventsResponse)
def get_cap_events(
    since: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> CapEventsResponse:
    return service.get_cap_events(since=since, limit=limit)
