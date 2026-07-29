"""Symbol search routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_SYMBOLS_READ
from app.schemas.market import SymbolResolveResponse, SymbolSearchResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])


@router.get("/search", response_model=SymbolSearchResponse)
def search_symbols(
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(25, ge=1, le=100),
    _=Depends(require_scopes([SCOPE_SYMBOLS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> SymbolSearchResponse:
    return service.search_symbols(query=q, limit=limit)


@router.get(
    "/resolve",
    response_model=SymbolResolveResponse,
    responses={
        404: {"description": "No exact security-master match"},
        409: {"description": "Symbol exists on more than one exchange"},
    },
)
def resolve_symbol(
    symbol: str = Query(..., min_length=1, max_length=64),
    _=Depends(require_scopes([SCOPE_SYMBOLS_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> SymbolResolveResponse:
    """Resolve one exact symbol without silently choosing between venues."""
    return service.resolve_symbol(symbol=symbol)
