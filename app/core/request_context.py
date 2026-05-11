"""Request ID injection and audit logging middleware."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.client_ip import get_client_ip

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("dataapi.audit")


class _RequestIdFilter(logging.Filter):
    """Inject the current request-ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get("-")
        return True


# Register the filter on the root logger so all loggers inherit it.
logging.getLogger().addFilter(_RequestIdFilter())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request-ID to state/context and write structured audit logs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = _request_id_var.set(request_id)

        start = time.perf_counter()
        client_ip = get_client_ip(request)

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        _request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        status = response.status_code

        log = logger.warning if status >= 400 else logger.info
        log(
            "request_complete method=%s path=%s status=%s duration_ms=%s "
            "client_ip=%s auth_type=%s auth_subject=%s",
            request.method,
            request.url.path,
            status,
            duration_ms,
            client_ip,
            getattr(request.state, "auth_type", "none"),
            getattr(request.state, "auth_subject", "anonymous"),
        )
        return response
