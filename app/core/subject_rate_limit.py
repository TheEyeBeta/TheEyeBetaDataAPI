"""Per-authenticated-subject rate limiting for sensitive admin endpoints."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request

logger = logging.getLogger("dataapi.ratelimit")


_all_buckets: list[dict[str, deque[float]]] = []


def reset_rate_limits() -> None:
    """Clear all rate-limit bucket state. Test-only; buckets are process-global."""
    for buckets in _all_buckets:
        buckets.clear()


def _make_rate_limiter(*, label: str, window_seconds: int, max_requests: int) -> Callable[[Request], None]:
    """Build a FastAPI dependency enforcing max_requests per subject per window_seconds.

    Each limiter gets its own bucket store, so tightening one endpoint's limit
    never starves requests to another endpoint sharing the same subject.
    """
    buckets: dict[str, deque[float]] = defaultdict(deque)
    _all_buckets.append(buckets)

    def _dependency(request: Request) -> None:
        subject = getattr(request.state, "auth_subject", None) or "anonymous"
        now = time.time()
        bucket = buckets[subject]

        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= max_requests:
            request_id = getattr(request.state, "request_id", None)
            logger.warning(
                "%s_rate_limit_exceeded auth_subject=%s bucket_size=%d",
                label,
                subject,
                len(bucket),
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"{label} rate limit exceeded ({max_requests} req/{window_seconds}s per subject)",
                    "request_id": request_id,
                },
                headers={"Retry-After": str(window_seconds)},
            )

        bucket.append(now)

    return _dependency


# Baseline limit for admin read/write endpoints.
require_admin_rate_limit = _make_rate_limiter(label="admin", window_seconds=60, max_requests=20)

# Account deletion also requires an approval code (see app/auth/account_approval.py);
# this caps guess attempts against that code to 1/min per subject on top of the
# baseline admin limit, regardless of code strength.
require_account_delete_rate_limit = _make_rate_limiter(
    label="account_delete", window_seconds=60, max_requests=1
)
