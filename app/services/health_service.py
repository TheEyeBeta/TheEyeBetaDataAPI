"""Health use-cases."""

from __future__ import annotations

from app.domain.errors import DatabaseUnavailableError
from app.repositories.interfaces import MarketDataRepository
from app.schemas.health import HealthResponse


class HealthService:
    """Service for health checks."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_health(self) -> HealthResponse:
        try:
            ok = self._repository.check_health()
        except DatabaseUnavailableError:
            ok = False
        return HealthResponse(status="healthy" if ok else "degraded", database=ok)
