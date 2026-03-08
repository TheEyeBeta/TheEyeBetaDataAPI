"""Internal operations use-cases."""

from __future__ import annotations

from app.auth.models import Principal
from app.repositories.interfaces import MarketDataRepository
from app.schemas.market import InternalJobResponse, InternalRebuildRequest


class InternalService:
    """Internal orchestration service."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def enqueue_rebuild(self, *, principal: Principal, request: InternalRebuildRequest) -> InternalJobResponse:
        params = {
            "ticker": request.ticker.upper() if request.ticker else None,
            "force": request.force,
            "reason": request.reason,
        }
        receipt = self._repository.enqueue_internal_job(
            operator_subject=principal.subject,
            command_type="rebuild_indicators",
            params=params,
        )
        return InternalJobResponse(
            status=receipt.status,
            command_id=receipt.command_id,
            command_type=receipt.command_type,
            created_at=receipt.created_at,
        )
