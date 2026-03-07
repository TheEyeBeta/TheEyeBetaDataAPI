"""Authentication schemas."""

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """JWT token issue request."""

    subject: str = Field(min_length=3, max_length=128)
    expires_minutes: int = Field(default=60, ge=5, le=1440)


class TokenResponse(BaseModel):
    """JWT token issue response."""

    access_token: str
    token_type: str = "bearer"
    expires_minutes: int
