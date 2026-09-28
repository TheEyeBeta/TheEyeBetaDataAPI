"""Policy enforcement decisions (locks, revocations, delegation) fail closed."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from app.auth.models import Principal, PrincipalType
from app.domain.errors import AuthenticationError, AuthorizationError, DatabaseUnavailableError
from app.policy.repository import PolicyRepository, enforce_policy


class _Result:
    def __init__(self, row) -> None:
        self._row = row

    def first(self):
        return self._row

    def mappings(self) -> _Result:
        return self


class _ScriptedSession:
    """Answers each execute() by matching a table name in the SQL."""

    def __init__(self, answers: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.answers = answers or {}
        self.error = error
        self.queries: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.queries.append((sql, dict(params or {})))
        if self.error is not None:
            raise self.error
        for table, row in self.answers.items():
            if table in sql:
                return _Result(row)
        return _Result(None)


def _delegated(**overrides) -> Principal:
    values = {
        "subject": "lens-user-1",
        "principal_type": PrincipalType.USER,
        "scopes": frozenset({"market:read"}),
        "client_id": "lens-backend",
        "tenant_id": "f6b70d15-2dfd-46b7-a217-3af37ed2b7dc",
        "product": "LENS",
        "token_id": "tok-1",
        "policy_version": 3,
        "delegated": True,
    }
    values.update(overrides)
    return Principal(**values)


def _service(**overrides) -> Principal:
    values = {
        "subject": "service:ai-advisor-production",
        "principal_type": PrincipalType.SERVICE,
        "scopes": frozenset({"market:read"}),
        "client_id": "ai-advisor-production",
        "token_id": "svc-tok",
    }
    values.update(overrides)
    return Principal(**values)


def test_entitled_delegated_principal_passes() -> None:
    session = _ScriptedSession({"dataapi_entitlements": (1,)})
    PolicyRepository(session).enforce(_delegated())
    lock_sql, lock_params = session.queries[1]
    assert "dataapi_locks" in lock_sql
    assert set(lock_params.values()) >= {"GLOBAL", "*", "TENANT", "APPLICATION", "SUBJECT", "CREDENTIAL", "tok-1"}


@pytest.mark.parametrize("missing", ["tenant_id", "client_id", "policy_version"])
def test_delegated_principal_without_binding_is_refused_before_any_query(missing: str) -> None:
    session = _ScriptedSession()
    with pytest.raises(AuthorizationError, match="no tenant binding"):
        PolicyRepository(session).enforce(_delegated(**{missing: None}))
    assert session.queries == []


def test_delegated_principal_no_longer_entitled_is_refused() -> None:
    with pytest.raises(AuthorizationError, match="no longer entitled"):
        PolicyRepository(_ScriptedSession()).enforce(_delegated())


def test_active_lock_blocks_delegated_principal() -> None:
    session = _ScriptedSession({"dataapi_entitlements": (1,), "dataapi_locks": ("lock-1",)})
    with pytest.raises(AuthorizationError, match="locked"):
        PolicyRepository(session).enforce(_delegated())


def test_revoked_credential_is_rejected() -> None:
    session = _ScriptedSession({"dataapi_entitlements": (1,), "dataapi_credential_revocations": ("rev-1",)})
    with pytest.raises(AuthenticationError, match="revoked"):
        PolicyRepository(session).enforce(_delegated())


def test_service_principal_is_checked_against_application_and_credential_locks() -> None:
    session = _ScriptedSession({"dataapi_locks": ("lock-1",)})
    with pytest.raises(AuthorizationError, match="locked"):
        PolicyRepository(session).enforce(_service())
    _, params = session.queries[0]
    assert "ai-advisor-production" in params.values()
    assert "svc-tok" in params.values()


def test_plain_user_principal_issues_no_policy_queries() -> None:
    session = _ScriptedSession()
    user = Principal(subject="user:u1", principal_type=PrincipalType.USER, scopes=frozenset({"market:read"}))
    PolicyRepository(session).enforce(user)
    assert session.queries == []


def test_database_failure_fails_closed_as_unavailable() -> None:
    session = _ScriptedSession(error=OperationalError("SELECT", {}, Exception("down")))
    with pytest.raises(DatabaseUnavailableError):
        enforce_policy(session, _service())


def test_lens_delegation_grant_requires_entitlement() -> None:
    with pytest.raises(AuthorizationError, match="not entitled"):
        PolicyRepository(_ScriptedSession()).grant_lens_delegation(client_id="lens-backend", subject="u1")


def test_lens_delegation_grant_returns_tenant_and_policy_version() -> None:
    session = _ScriptedSession({"dataapi_entitlements": {"tenant_id": "t-1", "policy_version": 4}})
    grant = PolicyRepository(session).grant_lens_delegation(client_id="lens-backend", subject="u1")
    assert (grant.tenant_id, grant.policy_version) == ("t-1", 4)


def test_lens_delegation_grant_respects_locks() -> None:
    session = _ScriptedSession(
        {"dataapi_entitlements": {"tenant_id": "t-1", "policy_version": 4}, "dataapi_locks": ("lock",)}
    )
    with pytest.raises(AuthorizationError, match="locked"):
        PolicyRepository(session).grant_lens_delegation(client_id="lens-backend", subject="u1")
