"""Market data routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_MARKET_READ
from app.schemas.market import MarketQuotesResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])


@router.get("/quotes", response_model=MarketQuotesResponse)
def get_quotes(
    symbols: str = Query(..., description="Comma-separated list of symbols"),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> MarketQuotesResponse:
    parsed = [part.strip().upper() for part in symbols.split(",") if part.strip()]
    return service.get_quotes(parsed)
