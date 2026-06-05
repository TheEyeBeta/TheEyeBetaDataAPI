"""Health use-cases."""

from __future__ import annotations

import logging

from app.domain.errors import DatabaseUnavailableError
from app.repositories.interfaces import MarketDataRepository
from app.schemas.health import HealthResponse

logger = logging.getLogger("dataapi.health")


def _check_redis() -> bool | None:
    """Ping Redis if configured. Returns None when Redis is not configured."""
    from app.core.config import settings

    if not settings.redis_url:
        return None
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5
        )
        return client.ping() is True
    except Exception:
        logger.warning("redis health check failed", exc_info=True)
        return False


class HealthService:
    """Service for health checks."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_health(self) -> HealthResponse:
        try:
            db_ok = self._repository.check_health()
        except DatabaseUnavailableError:
            db_ok = False

        redis_ok = _check_redis()
        return HealthResponse(
            status="healthy",
            database=db_ok,
            redis=redis_ok,
        )
