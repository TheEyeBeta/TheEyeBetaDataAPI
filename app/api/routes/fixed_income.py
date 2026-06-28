"""Fixed-income regime routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_fixed_income_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_MARKET_READ
from app.domain.errors import NotFoundAppError
from app.schemas.fixed_income import (
    FixedIncomeHistoryResponse,
    FixedIncomeRegimeResponse,
    FixedIncomeSignalsResponse,
)
from app.services.fixed_income_service import FixedIncomeService

router = APIRouter(tags=["fixed-income"])


@router.get("/regime", response_model=FixedIncomeRegimeResponse)
def regime(
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: FixedIncomeService = Depends(get_fixed_income_service),
) -> FixedIncomeRegimeResponse:
    snapshot = service.get_regime()
    if snapshot is None:
        raise NotFoundAppError("No fixed-income regime snapshot available")
    return snapshot


@router.get("/history", response_model=FixedIncomeHistoryResponse)
def history(
    start: date | None = Query(default=None, description="Start date (inclusive)"),
    end: date | None = Query(default=None, description="End date (inclusive)"),
    limit: int = Query(default=252, ge=1, le=5000, description="Max rows returned"),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: FixedIncomeService = Depends(get_fixed_income_service),
) -> FixedIncomeHistoryResponse:
    return service.get_history(start=start, end=end, limit=limit)


@router.get("/signals", response_model=FixedIncomeSignalsResponse)
def signals(
    limit: int = Query(default=50, ge=1, le=5000, description="Max rows returned"),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: FixedIncomeService = Depends(get_fixed_income_service),
) -> FixedIncomeSignalsResponse:
    return service.get_signals(limit=limit)
