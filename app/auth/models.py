"""Auth principal models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PrincipalType(str, Enum):
    """Allowed principal categories."""

    USER = "user"
    SERVICE = "service"


@dataclass(frozen=True)
class Principal:
    """Authenticated caller context used for authorization."""

    subject: str
    principal_type: PrincipalType
    scopes: frozenset[str]
    client_id: str | None = None
