"""Authentication schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ServiceTokenRequest(BaseModel):
    """Service token request payload."""

    model_config = ConfigDict(extra="forbid")

    requested_scopes: list[str] = Field(default_factory=list)

    @field_validator("requested_scopes")
    @classmethod
    def normalize_scopes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(normalized))


class ServiceTokenResponse(BaseModel):
    """Service token response payload."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    expires_minutes: int
    scopes: list[str]
    # Present only for clients with short_lived_tokens_enabled (Phase 3 opt-in).
    refresh_token: str | None = None
    refresh_expires_at: datetime | None = None


class RefreshTokenRequest(BaseModel):
    """Exchange a refresh token for a new access + rotated refresh token."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20, max_length=512)


class RefreshTokenResponse(ServiceTokenResponse):
    """Refresh response always includes a new refresh_token (rotate-on-use)."""

    refresh_token: str
    refresh_expires_at: datetime


class DelegatedTokenRequest(BaseModel):
    """Lens user token presented by an authenticated Lens backend."""

    model_config = ConfigDict(extra="forbid")

    subject_token: str = Field(min_length=20, max_length=16_384)


class DelegatedTokenResponse(ServiceTokenResponse):
    """Short-lived DataAPI token with a tenant-bound actor and subject."""

    tenant_id: str
    product: str = "LENS"
