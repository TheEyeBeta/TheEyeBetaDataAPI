"""Trade routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.api.dependencies.services import get_trades_service
from app.auth.dependencies import require_scopes
from app.auth.models import Principal
from app.auth.scopes import SCOPE_TRADES_WRITE
from app.domain.errors import ValidationAppError
from app.schemas.market import PlaceOrderRequest, PlaceOrderResponse
from app.services.trades_service import TradesService

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


@router.post("/orders", response_model=PlaceOrderResponse)
def place_order(
    request: PlaceOrderRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_scopes([SCOPE_TRADES_WRITE])),
    service: TradesService = Depends(get_trades_service),
) -> PlaceOrderResponse:
    """Trade write endpoint with idempotency and audit trail."""
    if not idempotency_key:
        raise ValidationAppError("Idempotency-Key header is required for trade writes")
    return service.place_order(principal=principal, request=request, idempotency_key=idempotency_key)
