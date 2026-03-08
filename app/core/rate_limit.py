"""Simple in-memory rate limiting middleware.

For multi-instance production, replace with Redis-backed limiter.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.client_ip import get_client_ip
from app.core.config import settings

try:
    import redis
except ImportError:  # pragma: no cover - fallback for minimal installs
    redis = None

# Interval (in requests) between sweeps that remove stale IP buckets.
_CLEANUP_EVERY = 500
logger = logging.getLogger("dataapi.ratelimit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-window limiter per client IP."""

    def __init__(self, app):
        super().__init__(app)
        self.window_seconds = 60
        self.max_requests = settings.rate_limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._request_count = 0
        self._redis_client = None
        self._redis_failed = False

        if settings.redis_url and redis is None:
            logger.warning("REDIS_URL is set but redis package is not installed; using in-memory limiter")
        elif settings.redis_url and redis is not None:
            self._redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=False, socket_timeout=0.2)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = get_client_ip(request)
        if self._redis_client is not None and self._is_over_limit_redis(client_ip):
            return self._limit_response(request)

        now = time.time()
        bucket = self._hits[client_ip]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            return self._limit_response(request)

        bucket.append(now)

        # Periodic cleanup: remove IPs whose buckets are empty (prevents memory leak).
        self._request_count += 1
        if self._request_count % _CLEANUP_EVERY == 0:
            stale = [ip for ip, b in self._hits.items() if not b]
            for ip in stale:
                del self._hits[ip]

        return await call_next(request)

    def _is_over_limit_redis(self, client_ip: str) -> bool:
        if self._redis_client is None:
            return False
        try:
            bucket = int(time.time() // self.window_seconds)
            key = f"{settings.rate_limit_redis_prefix}:{client_ip}:{bucket}"
            count = self._redis_client.incr(key)
            if count == 1:
                self._redis_client.expire(key, self.window_seconds + 5)
            return count > self.max_requests
        except Exception:
            # Fail open for availability, but record once and use in-memory limiter.
            if not self._redis_failed:
                logger.exception("redis rate limiter failed; falling back to in-memory limiter")
                self._redis_failed = True
            self._redis_client = None
            return False

    def _limit_response(self, request: Request) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded",
                    "request_id": request_id,
                }
            },
            headers={"Retry-After": "60"},
        )
