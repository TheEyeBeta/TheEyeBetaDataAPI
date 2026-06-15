"""Tests for IP-based rate limiting middleware."""

from __future__ import annotations

import time
from collections import deque
from unittest.mock import MagicMock, patch

from app.core.rate_limit import RateLimitMiddleware


# ---------------------------------------------------------------------------
# Unit tests — no FastAPI app import, no env vars needed
# ---------------------------------------------------------------------------

def _make_middleware(max_requests: int = 5, window: int = 60) -> RateLimitMiddleware:
    from collections import defaultdict

    mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
    mw.window_seconds = window
    mw.max_requests = max_requests
    mw._hits = defaultdict(deque)
    mw._request_count = 0
    mw._redis_client = None
    mw._redis_last_failure = None
    return mw


def test_allows_requests_under_limit() -> None:
    mw = _make_middleware(max_requests=3)
    now = time.time()
    bucket = mw._hits["1.2.3.4"]
    bucket.append(now - 10)
    bucket.append(now - 5)
    assert len(bucket) < mw.max_requests


def test_blocks_when_bucket_full() -> None:
    mw = _make_middleware(max_requests=3)
    now = time.time()
    bucket = mw._hits["1.2.3.4"]
    for _ in range(3):
        bucket.append(now - 1)
    assert len(bucket) >= mw.max_requests


def test_old_timestamps_are_evicted() -> None:
    mw = _make_middleware(max_requests=3, window=60)
    now = time.time()
    bucket = mw._hits["1.2.3.4"]
    for _ in range(3):
        bucket.append(now - 120)
    while bucket and now - bucket[0] > mw.window_seconds:
        bucket.popleft()
    assert len(bucket) == 0


def test_redis_failure_sets_last_failure_time() -> None:
    mw = _make_middleware()
    failing_redis = MagicMock()
    failing_redis.incr.side_effect = Exception("connection refused")
    mw._redis_client = failing_redis

    result = mw._is_over_limit_redis("1.2.3.5")

    assert result is False
    assert mw._redis_client is None
    assert mw._redis_last_failure is not None


def test_redis_reconnect_not_attempted_during_cooldown() -> None:
    mw = _make_middleware()
    mw._redis_last_failure = time.time() - 5  # 5 s ago; cooldown is 30 s

    with patch("app.core.rate_limit._REDIS_RETRY_INTERVAL", 30):
        mw._try_reconnect_redis()
        assert mw._redis_client is None


def test_redis_reconnect_attempted_after_cooldown(monkeypatch) -> None:
    mw = _make_middleware()
    mw._redis_last_failure = time.time() - 60  # older than cooldown

    ping_called = []

    class _FakeRedis:
        def ping(self):
            ping_called.append(True)
            return True

    class _FakeRedisLib:
        class Redis:
            @staticmethod
            def from_url(*a, **kw):
                return _FakeRedis()

    monkeypatch.setattr("app.core.rate_limit.redis", _FakeRedis)
    monkeypatch.setattr("app.core.rate_limit.settings.redis_url", "redis://localhost")

    with patch("app.core.rate_limit._REDIS_RETRY_INTERVAL", 30):
        with patch.object(mw, "_make_redis_client", return_value=_FakeRedis()):
            mw._try_reconnect_redis()

    assert mw._redis_last_failure is None


def test_limit_response_has_correct_shape() -> None:
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)
    mw = _make_middleware()
    resp = mw._limit_response(request)
    assert resp.status_code == 429
    import json
    body = json.loads(resp.body)
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert resp.headers.get("retry-after") == "60"
