"""Request/response models for admin account lifecycle endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

ALLOWED_PLANS = ("free", "starter", "pro", "enterprise")

# Mirrors the iam.users CHECK constraints (deploy/iam_user_api_key_schema.sql):
# lowercase, 3-320 chars, contains '@' not in the first position.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class CreateAccountRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_PATTERN)
    display_name: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    plan: str = Field(default="free", pattern="^(free|starter|pro|enterprise)$")


class AccountResponse(BaseModel):
    user_uuid: str
    email: str
    display_name: str | None = None
    organization: str | None = None
    plan: str | None = None
    is_active: bool
    created_at: datetime | None = None


class DeleteAccountRequest(BaseModel):
    approval_code: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=500)
