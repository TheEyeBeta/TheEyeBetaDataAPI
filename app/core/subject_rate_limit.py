"""Per-authenticated-subject rate limiting for sensitive admin endpoints."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import Request

logger = logging.getLogger("dataapi.ratelimit")

# Separate, tighter limits for admin operations.
_ADMIN_WINDOW_SECONDS = 60
_ADMIN_MAX_REQUESTS = 20

_subject_hits: dict[str, deque[float]] = defaultdict(deque)


def require_admin_rate_limit(request: Request) -> None:
    """FastAPI dependency: enforce per-subject rate limit on admin endpoints.

    Raises a JSONResponse (via HTTPException-style short-circuit) when the
    authenticated subject exceeds 20 admin requests per minute.
    """
    subject = getattr(request.state, "auth_subject", None) or "anonymous"
    now = time.time()
    bucket = _subject_hits[subject]

    while bucket and now - bucket[0] > _ADMIN_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= _ADMIN_MAX_REQUESTS:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "admin_rate_limit_exceeded auth_subject=%s bucket_size=%d",
            subject,
            len(bucket),
        )
        from fastapi import HTTPException
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Admin rate limit exceeded (20 req/min per subject)",
                "request_id": request_id,
            },
            headers={"Retry-After": "60"},
        )

    bucket.append(now)
