"""Macro indicator and regime routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_macro_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_MARKET_READ
from app.domain.errors import NotFoundAppError
from app.schemas.macro import (
    MacroLatestResponse,
    MacroRegimeResponse,
    MacroSeriesDetailResponse,
    MacroSeriesListResponse,
)
from app.services.macro_service import MacroService

router = APIRouter(tags=["macro"])


def _split_codes(codes: str | None) -> list[str] | None:
    if not codes:
        return None
    parsed = [c.strip() for c in codes.split(",") if c.strip()]
    return parsed or None


@router.get("/series", response_model=MacroSeriesListResponse)
def list_series(
    category: str | None = Query(default=None, description="Filter by category, e.g. inflation"),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MacroService = Depends(get_macro_service),
) -> MacroSeriesListResponse:
    return service.list_series(category=category)


@router.get("/latest", response_model=MacroLatestResponse)
def latest(
    codes: str | None = Query(
        default=None, description="Comma-separated series codes, e.g. GDPC1,UNRATE,DGS10"
    ),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MacroService = Depends(get_macro_service),
) -> MacroLatestResponse:
    return service.get_latest(codes=_split_codes(codes))


@router.get("/regime", response_model=MacroRegimeResponse)
def regime(
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MacroService = Depends(get_macro_service),
) -> MacroRegimeResponse:
    snapshot = service.get_regime()
    if snapshot is None:
        raise NotFoundAppError("No macro regime snapshot available")
    return snapshot


@router.get("/series/{code}", response_model=MacroSeriesDetailResponse)
def get_series(
    code: str,
    start: date | None = Query(default=None, description="Start date (inclusive)"),
    end: date | None = Query(default=None, description="End date (inclusive)"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max observations returned"),
    _=Depends(require_scopes([SCOPE_MARKET_READ])),
    service: MacroService = Depends(get_macro_service),
) -> MacroSeriesDetailResponse:
    detail = service.get_series(code=code, start=start, end=end, limit=limit)
    if detail is None:
        raise NotFoundAppError(f"Macro series not found: {code}")
    return detail
