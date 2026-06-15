"""Ticker detail, price history, and corporate action routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ANALYTICS_READ, SCOPE_MARKET_READ
from app.domain.errors import NotFoundAppError
from app.schemas.market import (
    CompanyFundamentalsResponse,
    CorporateActionsResponse,
    PriceHistoryResponse,
    TickerDetailResponse,
)
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/tickers", tags=["tickers"])


@router.get("/{ticker}", response_model=TickerDetailResponse)
def get_ticker(
    ticker: str,
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> TickerDetailResponse:
    result = service.get_ticker_detail(ticker=ticker.upper())
    if not result:
        raise NotFoundAppError(f"Ticker not found: {ticker.upper()}")
    return result


@router.get("/{ticker}/price-history", response_model=PriceHistoryResponse)
def get_price_history(
    ticker: str,
    start: date | None = Query(default=None, description="Start date (inclusive)"),
    end: date | None = Query(default=None, description="End date (inclusive)"),
    limit: int = Query(default=252, ge=1, le=2000),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> PriceHistoryResponse:
    return service.get_price_history(ticker=ticker.upper(), start=start, end=end, limit=limit)


@router.get("/{ticker}/corporate-actions", response_model=CorporateActionsResponse)
def get_corporate_actions(
    ticker: str,
    limit: int = Query(default=50, ge=1, le=500),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> CorporateActionsResponse:
    return service.get_corporate_actions(ticker=ticker.upper(), limit=limit)


@router.get("/{ticker}/fundamentals", response_model=CompanyFundamentalsResponse)
def get_fundamentals(
    ticker: str,
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> CompanyFundamentalsResponse:
    result = service.get_company_fundamentals(ticker=ticker.upper())
    if not result:
        raise NotFoundAppError(f"Fundamentals not found for: {ticker.upper()}")
    return result
