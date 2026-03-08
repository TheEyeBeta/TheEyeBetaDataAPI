"""Trades use-cases."""

from __future__ import annotations

from app.auth.models import Principal
from app.repositories.interfaces import MarketDataRepository
from app.schemas.market import PlaceOrderRequest, PlaceOrderResponse


class TradesService:
    """Write-focused trade execution service."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def place_order(
        self,
        *,
        principal: Principal,
        request: PlaceOrderRequest,
        idempotency_key: str,
    ) -> PlaceOrderResponse:
        result = self._repository.create_trade_order(
            operator_subject=principal.subject,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            idempotency_key=idempotency_key,
            limit_price=request.limit_price,
        )
        return PlaceOrderResponse(
            status=result.status,
            order_ref=result.order_ref,
            idempotency_key=result.idempotency_key,
            symbol=result.symbol,
            side=result.side,
            quantity=result.quantity,
            executed_price=result.executed_price,
            total_cost=result.total_cost,
            accepted_at=result.accepted_at,
            idempotent_replay=result.idempotent_replay,
        )
