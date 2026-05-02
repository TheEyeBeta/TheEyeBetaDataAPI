"""Quarterly financial statement routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ANALYTICS_READ
from app.schemas.market import (
    BalanceSheetsResponse,
    CashFlowsResponse,
    IncomeStatementsResponse,
    QualityMetricsResponse,
)
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/financials", tags=["financials"])

_LIMIT_QUERY = Query(default=12, ge=1, le=40, description="Number of quarterly periods")


@router.get("/{ticker}/income", response_model=IncomeStatementsResponse)
def get_income(
    ticker: str,
    limit: int = _LIMIT_QUERY,
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> IncomeStatementsResponse:
    return service.get_income_statements(ticker=ticker.upper(), limit=limit)


@router.get("/{ticker}/balance", response_model=BalanceSheetsResponse)
def get_balance(
    ticker: str,
    limit: int = _LIMIT_QUERY,
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> BalanceSheetsResponse:
    return service.get_balance_sheets(ticker=ticker.upper(), limit=limit)


@router.get("/{ticker}/cashflow", response_model=CashFlowsResponse)
def get_cashflow(
    ticker: str,
    limit: int = _LIMIT_QUERY,
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> CashFlowsResponse:
    return service.get_cash_flows(ticker=ticker.upper(), limit=limit)


@router.get("/{ticker}/quality", response_model=QualityMetricsResponse)
def get_quality(
    ticker: str,
    limit: int = _LIMIT_QUERY,
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> QualityMetricsResponse:
    return service.get_quality_metrics(ticker=ticker.upper(), limit=limit)
