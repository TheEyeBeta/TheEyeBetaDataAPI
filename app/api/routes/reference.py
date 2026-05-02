"""Reference / lookup data routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_MARKET_READ
from app.schemas.market import (
    CountriesResponse,
    CurrenciesResponse,
    ExchangesResponse,
    IndustriesResponse,
    SectorsResponse,
    TradingCalendarResponse,
)
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/reference", tags=["reference"])


@router.get("/countries", response_model=CountriesResponse)
def list_countries(
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> CountriesResponse:
    return service.get_countries()


@router.get("/currencies", response_model=CurrenciesResponse)
def list_currencies(
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> CurrenciesResponse:
    return service.get_currencies()


@router.get("/exchanges", response_model=ExchangesResponse)
def list_exchanges(
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> ExchangesResponse:
    return service.get_exchanges()


@router.get("/sectors", response_model=SectorsResponse)
def list_sectors(
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> SectorsResponse:
    return service.get_sectors()


@router.get("/industries", response_model=IndustriesResponse)
def list_industries(
    sector_id: int | None = Query(default=None, description="Filter by sector ID"),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> IndustriesResponse:
    return service.get_industries(sector_id=sector_id)


@router.get("/calendar", response_model=TradingCalendarResponse)
def list_trading_calendar(
    start: date | None = Query(default=None, description="Start date (inclusive)"),
    end: date | None = Query(default=None, description="End date (inclusive)"),
    limit: int = Query(default=90, ge=1, le=500),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> TradingCalendarResponse:
    return service.get_trading_calendar(start=start, end=end, limit=limit)
