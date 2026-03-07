"""Simple in-memory rate limiting middleware.

For multi-instance production, replace with Redis-backed limiter.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.client_ip import get_client_ip
from app.core.config import settings

# Interval (in requests) between sweeps that remove stale IP buckets.
_CLEANUP_EVERY = 500


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-window limiter per client IP."""

    def __init__(self, app):
        super().__init__(app)
        self.window_seconds = 60
        self.max_requests = settings.rate_limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._request_count = 0

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = get_client_ip(request)
        now = time.time()
        bucket = self._hits[client_ip]

        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )

        bucket.append(now)

        # Periodic cleanup: remove IPs whose buckets are empty (prevents memory leak).
        self._request_count += 1
        if self._request_count % _CLEANUP_EVERY == 0:
            stale = [ip for ip, b in self._hits.items() if not b]
            for ip in stale:
                del self._hits[ip]

        return await call_next(request)
