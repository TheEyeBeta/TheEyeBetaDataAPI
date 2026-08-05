"""Tests for the per-subject admin rate limiters."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.subject_rate_limit import _make_rate_limiter, require_account_delete_rate_limit, require_admin_rate_limit


def _request(subject: str) -> Request:
    req = Request(scope={"type": "http", "headers": []})
    req.state.auth_subject = subject
    return req


def test_admin_rate_limit_allows_up_to_20_per_minute() -> None:
    subject = "admin:test-admin-limit"
    for _ in range(20):
        require_admin_rate_limit(_request(subject))
    with pytest.raises(HTTPException) as exc_info:
        require_admin_rate_limit(_request(subject))
    assert exc_info.value.status_code == 429


def test_account_delete_rate_limit_allows_only_1_per_minute() -> None:
    subject = "admin:test-delete-limit"
    require_account_delete_rate_limit(_request(subject))
    with pytest.raises(HTTPException) as exc_info:
        require_account_delete_rate_limit(_request(subject))
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in exc_info.value.headers


def test_account_delete_rate_limit_is_independent_per_subject() -> None:
    require_account_delete_rate_limit(_request("admin:subject-a"))
    # A different subject still gets its own first attempt.
    require_account_delete_rate_limit(_request("admin:subject-b"))


def test_account_delete_rate_limit_has_its_own_bucket_from_admin_limit() -> None:
    """Hitting the 20/min admin limiter must not also exhaust the 1/min delete limiter."""
    subject = "admin:shared-subject"
    for _ in range(5):
        require_admin_rate_limit(_request(subject))
    # The strict delete limiter's bucket is untouched by the calls above.
    require_account_delete_rate_limit(_request(subject))


def test_make_rate_limiter_message_reflects_config() -> None:
    limiter = _make_rate_limiter(label="custom", window_seconds=30, max_requests=2)
    subject = "admin:custom-limiter"
    limiter(_request(subject))
    limiter(_request(subject))
    with pytest.raises(HTTPException) as exc_info:
        limiter(_request(subject))
    assert "custom" in exc_info.value.detail["message"]
    assert "2 req/30s" in exc_info.value.detail["message"]
