"""Analytics routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ANALYTICS_READ
from app.schemas.market import AnalyticsSnapshotResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/snapshots/{ticker}", response_model=AnalyticsSnapshotResponse)
def get_snapshot(
    ticker: str,
    _=Depends(require_scopes([SCOPE_ANALYTICS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> AnalyticsSnapshotResponse:
    return service.get_analytics_snapshot(ticker=ticker)
