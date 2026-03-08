"""Error response contracts."""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Typed API error detail payload."""

    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Top-level error response payload."""

    error: ErrorDetail
