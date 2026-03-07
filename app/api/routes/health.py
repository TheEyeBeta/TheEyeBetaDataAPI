"""Health check routes."""

from fastapi import APIRouter

from app.db.queries import db_health
from app.db.session import get_db_session
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return API and DB health status."""
    session = get_db_session()
    try:
        ok = db_health(session)
        return HealthResponse(status="healthy" if ok else "degraded", database=ok)
    finally:
        session.close()
