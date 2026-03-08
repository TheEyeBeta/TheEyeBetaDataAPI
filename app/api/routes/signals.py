"""Signals routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_signals_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_SIGNALS_READ
from app.schemas.market import SignalsLatestResponse
from app.services.signals_service import SignalsService

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.get("/latest", response_model=SignalsLatestResponse)
def get_latest_signals(
    ticker: str | None = Query(default=None, min_length=1, max_length=16),
    limit: int = Query(default=20, ge=1, le=200),
    _=Depends(require_scopes([SCOPE_SIGNALS_READ])),
    service: SignalsService = Depends(get_signals_service),
) -> SignalsLatestResponse:
    """Return latest signals with optional ticker filter."""
    return service.get_latest(ticker=ticker, limit=limit)
