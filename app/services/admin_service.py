"""Admin use-cases."""

from __future__ import annotations

from app.repositories.interfaces import MarketDataRepository
from app.schemas.market import AdminAuditEventResponse, AdminAuditEventsResponse


class AdminService:
    """Admin read operations."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_audit_events(self, *, limit: int, category: str | None) -> AdminAuditEventsResponse:
        events = self._repository.get_admin_audit_events(limit=limit, category=category)
        return AdminAuditEventsResponse(
            events=[
                AdminAuditEventResponse(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    event_category=event.event_category,
                    source_type=event.source_type,
                    source_id=event.source_id,
                    target_type=event.target_type,
                    target_id=event.target_id,
                    severity=event.severity,
                    payload=event.payload,
                    created_at=event.created_at,
                )
                for event in events
            ]
        )
