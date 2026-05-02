"""Technical, risk, valuation, and returns indicator routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ANALYTICS_READ
from app.schemas.market import (
    ReturnsSnapshotResponse,
    RiskIndicatorsResponse,
    TechnicalIndicatorsResponse,
    ValuationIndicatorsResponse,
)
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/indicators", tags=["indicators"])


def _date_params() -> tuple:
    return (
        Query(default=None, description="Start date (inclusive)"),
        Query(default=None, description="End date (inclusive)"),
        Query(default=252, ge=1, le=2000, description="Max rows returned"),
    )


@router.get("/{ticker}/technical", response_model=TechnicalIndicatorsResponse)
def get_technical(
    ticker: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    limit: int = Query(default=252, ge=1, le=2000),
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> TechnicalIndicatorsResponse:
    return service.get_technical_indicators(ticker=ticker.upper(), start=start, end=end, limit=limit)


@router.get("/{ticker}/risk", response_model=RiskIndicatorsResponse)
def get_risk(
    ticker: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    limit: int = Query(default=252, ge=1, le=2000),
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> RiskIndicatorsResponse:
    return service.get_risk_indicators(ticker=ticker.upper(), start=start, end=end, limit=limit)


@router.get("/{ticker}/valuation", response_model=ValuationIndicatorsResponse)
def get_valuation(
    ticker: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    limit: int = Query(default=252, ge=1, le=2000),
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> ValuationIndicatorsResponse:
    return service.get_valuation_indicators(ticker=ticker.upper(), start=start, end=end, limit=limit)


@router.get("/{ticker}/returns", response_model=ReturnsSnapshotResponse)
def get_returns(
    ticker: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    limit: int = Query(default=252, ge=1, le=2000),
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> ReturnsSnapshotResponse:
    return service.get_returns_snapshot(ticker=ticker.upper(), start=start, end=end, limit=limit)
