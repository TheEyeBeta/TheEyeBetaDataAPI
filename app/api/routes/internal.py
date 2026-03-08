"""Internal operations routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.services import get_internal_service
from app.auth.dependencies import require_scopes
from app.auth.models import Principal
from app.auth.scopes import SCOPE_INTERNAL_JOBS
from app.schemas.market import InternalJobResponse, InternalRebuildRequest
from app.services.internal_service import InternalService

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


@router.post("/jobs/rebuild-indicators", response_model=InternalJobResponse)
def rebuild_indicators(
    request: InternalRebuildRequest | None = None,
    principal: Principal = Depends(require_scopes([SCOPE_INTERNAL_JOBS])),
    service: InternalService = Depends(get_internal_service),
) -> InternalJobResponse:
    """Queue a rebuild-indicators command in command log."""
    return service.enqueue_rebuild(principal=principal, request=request or InternalRebuildRequest())
