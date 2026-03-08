"""Backward-compatible security exports."""

from app.auth.dependencies import get_principal as require_auth
from app.auth.tokens import create_service_access_token as create_access_token

__all__ = ["require_auth", "create_access_token"]
