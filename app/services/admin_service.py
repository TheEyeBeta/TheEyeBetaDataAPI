"""Admin use-cases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.domain.errors import DatabaseUnavailableError
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

    def get_dashboard_data(self) -> dict[str, Any]:
        """Gather all data needed for the admin dashboard."""
        # Database connection check
        db_connected = False
        db_version = "unavailable"
        try:
            db_connected = self._repository.check_health()
            db_version = self._repository.get_database_version()
        except DatabaseUnavailableError:
            pass

        # Table row counts
        table_counts: list[dict[str, Any]] = []
        try:
            table_counts = self._repository.get_table_row_counts()
        except DatabaseUnavailableError:
            pass

        # Engine worker heartbeats
        workers = self._repository.get_engine_worker_heartbeats()

        # Active ticker count
        ticker_count = self._repository.get_active_ticker_count()

        # Service clients
        service_clients = self._repository.get_service_client_summary()

        # Recent audit events
        recent_events: list[dict[str, Any]] = []
        try:
            events = self._repository.get_admin_audit_events(limit=10)
            recent_events = [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "event_category": e.event_category,
                    "severity": e.severity,
                    "created_at": str(e.created_at) if e.created_at else None,
                }
                for e in events
            ]
        except DatabaseUnavailableError:
            pass

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api": {
                "name": settings.app_name,
                "version": settings.app_version,
                "environment": settings.environment,
                "host": settings.api_host,
                "port": settings.api_port,
                "status": "running",
            },
            "database": {
                "connected": db_connected,
                "version": db_version,
                "url_masked": _mask_db_url(settings.database_url),
            },
            "tables": table_counts,
            "engine_workers": workers,
            "active_tickers": ticker_count,
            "service_clients": service_clients,
            "recent_events": recent_events,
        }

    def execute_query(self, query: str, limit: int = 100) -> dict[str, Any]:
        """Execute a read-only query and return results."""
        rows = self._repository.execute_readonly_query(query, limit=limit)
        return {"query": query, "row_count": len(rows), "rows": rows}


def _mask_db_url(url: str) -> str:
    """Mask password in database URL for display."""
    if "://" not in url:
        return "***"
    try:
        prefix, rest = url.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.rsplit("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{prefix}://{user}:***@{host_part}"
        return f"{prefix}://***@{rest}"
    except Exception:
        return "***"
