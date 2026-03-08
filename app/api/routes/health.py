"""Health check routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies.services import get_health_service
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(health_service: HealthService = Depends(get_health_service)) -> HealthResponse:
    """Return API and DB health status."""
    return health_service.get_health()
