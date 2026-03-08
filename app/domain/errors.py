"""Domain and application-level errors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    """Base typed error for API-safe error handling."""

    status_code: int
    code: str
    message: str


class AuthenticationError(AppError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(status_code=401, code="AUTHENTICATION_FAILED", message=message)


class AuthorizationError(AppError):
    """Caller lacks required scope/role."""

    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(status_code=403, code="FORBIDDEN", message=message)


class ValidationAppError(AppError):
    """Input or business validation failed."""

    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(status_code=422, code="VALIDATION_ERROR", message=message)


class ConflictAppError(AppError):
    """Conflict with current resource state."""

    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(status_code=409, code="CONFLICT", message=message)


class NotFoundAppError(AppError):
    """Resource not found."""

    def __init__(self, message: str = "Not found") -> None:
        super().__init__(status_code=404, code="NOT_FOUND", message=message)


class DatabaseUnavailableError(AppError):
    """Database is not available."""

    def __init__(self, message: str = "Database unavailable") -> None:
        super().__init__(status_code=503, code="DATABASE_UNAVAILABLE", message=message)


class NotImplementedAppError(AppError):
    """Capability intentionally not implemented yet."""

    def __init__(self, message: str = "Capability not implemented") -> None:
        super().__init__(status_code=501, code="NOT_IMPLEMENTED", message=message)
