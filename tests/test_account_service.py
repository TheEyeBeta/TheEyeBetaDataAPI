"""Tests for AccountService create/delete against a fake DB session."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.domain.errors import ApprovalRequiredError, ConflictAppError, DatabaseUnavailableError, NotFoundAppError
from app.services.account_service import AccountService


@pytest.fixture(autouse=True)
def _reset_approval_code():
    original = settings.admin_account_approval_code
    settings.admin_account_approval_code = "correct-horse-battery-staple"
    yield
    settings.admin_account_approval_code = original


class _FakeMappings:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def first(self) -> dict | None:
        return self._row


class _FakeResult:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._row)


class _FakeSession:
    """Routes execute() calls by SQL shape; records commit/rollback."""

    def __init__(self, *, insert_row: dict | None = None, update_row: dict | None = None, raise_on_insert: Exception | None = None, raise_on_update: Exception | None = None) -> None:
        self._insert_row = insert_row
        self._update_row = update_row
        self._raise_on_insert = raise_on_insert
        self._raise_on_update = raise_on_update
        self.executed: list[str] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement, params=None):  # noqa: ANN001, ANN201
        sql = str(statement)
        self.executed.append(sql)
        if "INSERT INTO iam.users" in sql:
            if self._raise_on_insert:
                raise self._raise_on_insert
            return _FakeResult(self._insert_row)
        if "UPDATE iam.users" in sql:
            if self._raise_on_update:
                raise self._raise_on_update
            return _FakeResult(self._update_row)
        # iam.user_api_key_events insert (event log) — no return value needed.
        return _FakeResult(None)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        pass


def _new_user_row() -> dict:
    return {
        "user_uuid": "11111111-1111-1111-1111-111111111111",
        "email": "new.user@example.com",
        "display_name": "New User",
        "organization": None,
        "plan": "free",
        "is_active": True,
        "created_at": None,
    }


# --- create_account --------------------------------------------------------


def test_create_account_success() -> None:
    session = _FakeSession(insert_row=_new_user_row())
    service = AccountService(session)

    result = service.create_account(
        email="new.user@example.com",
        display_name="New User",
        organization=None,
        plan="free",
        actor_subject="admin:alice",
    )

    assert result["email"] == "new.user@example.com"
    assert session.committed is True
    assert any("user_api_key_events" in sql for sql in session.executed)


def test_create_account_conflict_rolls_back() -> None:
    session = _FakeSession(raise_on_insert=IntegrityError("stmt", {}, Exception("dup")))
    service = AccountService(session)

    with pytest.raises(ConflictAppError):
        service.create_account(
            email="dup@example.com",
            display_name=None,
            organization=None,
            plan="free",
            actor_subject="admin:alice",
        )
    assert session.rolled_back is True


def test_create_account_db_error_maps_to_unavailable() -> None:
    session = _FakeSession(raise_on_insert=SQLAlchemyError("boom"))
    service = AccountService(session)

    with pytest.raises(DatabaseUnavailableError):
        service.create_account(
            email="x@example.com",
            display_name=None,
            organization=None,
            plan="free",
            actor_subject="admin:alice",
        )
    assert session.rolled_back is True


# --- delete_account ----------------------------------------------------------


def test_delete_account_requires_approval_before_touching_db() -> None:
    session = _FakeSession()
    service = AccountService(session)

    with pytest.raises(ApprovalRequiredError):
        service.delete_account(
            user_uuid="11111111-1111-1111-1111-111111111111",
            approval_code="wrong",
            actor_subject="admin:alice",
            reason="test",
        )
    # The gate must reject before any SQL is issued.
    assert session.executed == []
    assert session.committed is False


def test_delete_account_success() -> None:
    session = _FakeSession(
        update_row={
            "user_uuid": "11111111-1111-1111-1111-111111111111",
            "email": "gone@example.com",
            "is_active": False,
        }
    )
    service = AccountService(session)

    result = service.delete_account(
        user_uuid="11111111-1111-1111-1111-111111111111",
        approval_code="correct-horse-battery-staple",
        actor_subject="admin:alice",
        reason="requested by user",
    )

    assert result["is_active"] is False
    assert session.committed is True
    assert any("user_api_key_events" in sql for sql in session.executed)


def test_delete_account_not_found() -> None:
    session = _FakeSession(update_row=None)
    service = AccountService(session)

    with pytest.raises(NotFoundAppError):
        service.delete_account(
            user_uuid="00000000-0000-0000-0000-000000000000",
            approval_code="correct-horse-battery-staple",
            actor_subject="admin:alice",
            reason=None,
        )
    assert session.rolled_back is True


def test_delete_account_db_error_maps_to_unavailable() -> None:
    session = _FakeSession(raise_on_update=SQLAlchemyError("boom"))
    service = AccountService(session)

    with pytest.raises(DatabaseUnavailableError):
        service.delete_account(
            user_uuid="11111111-1111-1111-1111-111111111111",
            approval_code="correct-horse-battery-staple",
            actor_subject="admin:alice",
            reason=None,
        )
    assert session.rolled_back is True
