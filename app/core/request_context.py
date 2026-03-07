"""Request ID and audit logging middleware."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.client_ip import get_client_ip

logger = logging.getLogger("dataapi.audit")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request id and write basic audit logs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        start = time.perf_counter()
        client_ip = get_client_ip(request)

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%s client_ip=%s auth_type=%s auth_subject=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_ip,
            getattr(request.state, "auth_type", "none"),
            getattr(request.state, "auth_subject", "anonymous"),
        )
        return response
