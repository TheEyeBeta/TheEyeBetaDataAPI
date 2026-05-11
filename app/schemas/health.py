"""Health response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health payload."""

    status: str
    database: bool
    redis: bool | None = None
