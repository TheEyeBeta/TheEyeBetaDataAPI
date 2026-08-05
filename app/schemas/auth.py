"""Authentication schemas."""

from pydantic import BaseModel, Field, field_validator


class ServiceTokenRequest(BaseModel):
    """Service token request payload."""

    requested_scopes: list[str] = Field(default_factory=list)

    @field_validator("requested_scopes")
    @classmethod
    def normalize_scopes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(normalized))


class ServiceTokenResponse(BaseModel):
    """Service token response payload."""

    access_token: str
    token_type: str = "bearer"
    expires_minutes: int
    scopes: list[str]


class DelegatedTokenRequest(BaseModel):
    """Lens user token presented by an authenticated Lens backend."""

    subject_token: str = Field(min_length=20, max_length=16_384)


class DelegatedTokenResponse(ServiceTokenResponse):
    """Short-lived DataAPI token with a tenant-bound actor and subject."""

    tenant_id: str
    product: str = "LENS"
