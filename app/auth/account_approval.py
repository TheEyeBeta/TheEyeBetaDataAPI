"""Approval-code gate for destructive account actions.

Fail-closed: if no code word is configured on this server, the action is
refused rather than silently allowed. Comparison uses ``hmac.compare_digest``
to avoid leaking the expected value through response-timing differences.
"""

from __future__ import annotations

import hmac

from app.core.config import settings
from app.domain.errors import ApprovalRequiredError


def require_account_approval(provided_code: str | None) -> None:
    """Raise ApprovalRequiredError unless provided_code matches the configured code word."""
    expected = settings.admin_account_approval_code
    if not expected or not expected.strip():
        raise ApprovalRequiredError(
            "Account approval code is not configured on this server; "
            "set ADMIN_ACCOUNT_APPROVAL_CODE to enable this action."
        )

    if not provided_code:
        raise ApprovalRequiredError("Invalid or missing approval code.")

    # Compare as UTF-8 bytes: hmac.compare_digest raises TypeError on non-ASCII
    # str input, which would otherwise surface as a 500 instead of a clean 403.
    provided_bytes = provided_code.strip().encode("utf-8")
    expected_bytes = expected.strip().encode("utf-8")
    if not hmac.compare_digest(provided_bytes, expected_bytes):
        raise ApprovalRequiredError("Invalid or missing approval code.")
