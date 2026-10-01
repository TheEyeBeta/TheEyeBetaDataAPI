"""Central exception handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import AppError

logger = logging.getLogger("dataapi.errors")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


# Keys of a pydantic error that are safe to return. "input" echoes the caller's
# raw value (possibly a secret such as approval_code or refresh_token); "ctx"
# can hold exception objects; "url" is noise.
_SAFE_VALIDATION_KEYS = ("type", "loc", "msg")


def _public_validation_errors(exc: RequestValidationError) -> list[dict]:
    return [{key: error[key] for key in _SAFE_VALIDATION_KEYS if key in error} for error in exc.errors()]


def register_error_handlers(app: FastAPI) -> None:
    """Register all application-level error handlers."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "request_id": _request_id(request)}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never str(exc): since FastAPI 0.13x it appends the handler's source file
        # path and line number. Only type/loc/msg of each error reach the client.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_ERROR",
                    "message": str(_public_validation_errors(exc)),
                    "request_id": _request_id(request),
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Internal server error",
                    "request_id": _request_id(request),
                }
            },
        )
