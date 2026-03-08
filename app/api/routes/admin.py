"""Admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.services import get_admin_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ADMIN_READ
from app.schemas.market import AdminAuditEventsResponse
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/audit-events", response_model=AdminAuditEventsResponse)
def get_audit_events(
    limit: int = Query(default=50, ge=1, le=500),
    category: str | None = Query(default=None, max_length=80),
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: AdminService = Depends(get_admin_service),
) -> AdminAuditEventsResponse:
    """Return admin audit events from orchestration tables."""
    return service.get_audit_events(limit=limit, category=category)
