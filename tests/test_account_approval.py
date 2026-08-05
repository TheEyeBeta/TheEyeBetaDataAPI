"""Tests for the fail-closed admin-account approval gate."""

import pytest

from app.auth.account_approval import require_account_approval
from app.core.config import settings
from app.domain.errors import ApprovalRequiredError


@pytest.fixture(autouse=True)
def _reset_approval_code():
    original = settings.admin_account_approval_code
    yield
    settings.admin_account_approval_code = original


def test_fails_closed_when_not_configured() -> None:
    settings.admin_account_approval_code = None
    with pytest.raises(ApprovalRequiredError, match="not configured"):
        require_account_approval("anything")


def test_fails_closed_when_configured_blank() -> None:
    settings.admin_account_approval_code = "   "
    with pytest.raises(ApprovalRequiredError, match="not configured"):
        require_account_approval("anything")


def test_rejects_missing_code() -> None:
    settings.admin_account_approval_code = "correct-horse-battery-staple"
    with pytest.raises(ApprovalRequiredError, match="Invalid or missing"):
        require_account_approval(None)


def test_rejects_wrong_code() -> None:
    settings.admin_account_approval_code = "correct-horse-battery-staple"
    with pytest.raises(ApprovalRequiredError, match="Invalid or missing"):
        require_account_approval("wrong-code")


def test_accepts_matching_code() -> None:
    settings.admin_account_approval_code = "correct-horse-battery-staple"
    require_account_approval("correct-horse-battery-staple")


def test_accepts_matching_code_with_surrounding_whitespace() -> None:
    settings.admin_account_approval_code = "correct-horse-battery-staple"
    require_account_approval("  correct-horse-battery-staple  ")


def test_rejects_non_ascii_code_cleanly_instead_of_crashing() -> None:
    settings.admin_account_approval_code = "correct-horse-battery-staple"
    with pytest.raises(ApprovalRequiredError, match="Invalid or missing"):
        require_account_approval("wrong-ééé-code")
