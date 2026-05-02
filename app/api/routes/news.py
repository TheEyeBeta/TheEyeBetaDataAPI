"""News routes — market-wide and per-ticker."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_MARKET_READ
from app.schemas.market import MarketNewsResponse, TickerNewsResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.get("/market", response_model=MarketNewsResponse)
def get_market_news(
    limit: int = Query(default=20, ge=1, le=100),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> MarketNewsResponse:
    return service.get_market_news(limit=limit)


@router.get("/ticker/{ticker}", response_model=TickerNewsResponse)
def get_ticker_news(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> TickerNewsResponse:
    return service.get_ticker_news(ticker=ticker.upper(), limit=limit)
