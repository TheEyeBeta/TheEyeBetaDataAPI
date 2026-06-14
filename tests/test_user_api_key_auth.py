"""Tests for end-user API key validation and bearer routing."""

import pytest
from starlette.requests import Request

from app.auth import dependencies
from app.auth.models import PrincipalType
from app.auth.user_api_keys import (
    USER_API_KEY_PREFIX,
    _extract_key_prefix,
    is_user_api_key,
    verify_user_api_key,
)
from app.domain.errors import AuthenticationError

VALID_PREFIX = "0123456789abcdef"
VALID_KEY = f"{USER_API_KEY_PREFIX}{VALID_PREFIX}_secret-part_with_underscores"


# --- prefix parsing -------------------------------------------------------


def test_is_user_api_key() -> None:
    assert is_user_api_key(VALID_KEY) is True
    assert is_user_api_key("teb_sk_deadbeef_xyz") is False
    assert is_user_api_key("eyJhbGciOi...") is False


def test_extract_key_prefix_valid() -> None:
    assert _extract_key_prefix(VALID_KEY) == VALID_PREFIX


@pytest.mark.parametrize(
    "raw_key",
    [
        "teb_uk_short_secret",  # prefix too short
        f"{USER_API_KEY_PREFIX}{VALID_PREFIX}",  # no secret segment
        f"{USER_API_KEY_PREFIX}{VALID_PREFIX}_",  # empty secret
        f"{USER_API_KEY_PREFIX}zzzzzzzzzzzzzzzz_secret",  # non-hex prefix
        f"{USER_API_KEY_PREFIX}0123456789abcdefNO_UNDERSCORE",  # prefix not followed by '_'
        "not-a-key",
    ],
)
def test_extract_key_prefix_rejects_bad(raw_key: str) -> None:
    with pytest.raises(AuthenticationError):
        _extract_key_prefix(raw_key)


# --- DB verification (fake session) --------------------------------------


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
    """Returns the seeded row for the lookup SELECT, nothing for writes."""

    def __init__(self, row: dict | None) -> None:
        self._row = row
        self.executed: list[tuple[str, dict | None]] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement, params=None):  # noqa: ANN001, ANN201
        sql = str(statement)
        self.executed.append((sql, params))
        if "FROM iam.user_api_keys k" in sql:
            return _FakeResult(self._row)
        return _FakeResult(None)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        pass


def _success_row() -> dict:
    return {
        "key_uuid": "11111111-1111-1111-1111-111111111111",
        "user_uuid": "22222222-2222-2222-2222-222222222222",
        "scopes": ["market:read", "portfolio:read"],
        "key_enabled": True,
        "is_expired": False,
        "user_active": True,
    }


def test_verify_user_api_key_success() -> None:
    session = _FakeSession(_success_row())
    principal = verify_user_api_key(VALID_KEY, session=session, client_ip="203.0.113.10")

    assert principal.principal_type == PrincipalType.USER
    assert principal.subject == "user:22222222-2222-2222-2222-222222222222"
    assert principal.scopes == frozenset({"market:read", "portfolio:read"})
    assert session.committed is True
    # last_used_at is recorded on success.
    assert any("UPDATE iam.user_api_keys" in sql and "last_used" in sql for sql, _ in session.executed)
    # No rejection event written on the happy path.
    assert not any("user_api_key_events" in sql for sql, _ in session.executed)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"key_enabled": False}, "key_revoked"),
        ({"is_expired": True}, "key_expired"),
        ({"user_active": False}, "user_inactive"),
    ],
)
def test_verify_user_api_key_rejects_and_audits(mutation: dict, reason: str) -> None:
    row = _success_row()
    row.update(mutation)
    session = _FakeSession(row)

    with pytest.raises(AuthenticationError):
        verify_user_api_key(VALID_KEY, session=session, client_ip="203.0.113.10")

    event = [(sql, params) for sql, params in session.executed if "user_api_key_events" in sql]
    assert event, "rejection should be audited"
    assert reason in event[0][1]["event_payload"]
    assert session.committed is True


def test_verify_user_api_key_unknown_key() -> None:
    session = _FakeSession(None)
    with pytest.raises(AuthenticationError):
        verify_user_api_key(VALID_KEY, session=session, client_ip=None)
    event = [(sql, params) for sql, params in session.executed if "user_api_key_events" in sql]
    assert event and "invalid_key" in event[0][1]["event_payload"]


# --- bearer routing -------------------------------------------------------


def _make_request(authorization: str) -> Request:
    scope = {
        "type": "http",
        "headers": [(b"authorization", authorization.encode())],
        "client": ("203.0.113.10", 4444),
        "state": {},
    }
    return Request(scope)


def test_get_principal_routes_user_api_key(monkeypatch) -> None:
    captured: dict = {}

    def _fake_verify(raw_key, *, client_ip):  # noqa: ANN001, ANN202
        captured["raw_key"] = raw_key
        captured["client_ip"] = client_ip
        from app.auth.models import Principal

        return Principal(
            subject="user:22222222-2222-2222-2222-222222222222",
            principal_type=PrincipalType.USER,
            scopes=frozenset({"market:read"}),
        )

    def _boom_decode(_token):  # noqa: ANN202
        raise AssertionError("JWT path must not run for teb_uk_ keys")

    monkeypatch.setattr(dependencies, "verify_user_api_key", _fake_verify)
    monkeypatch.setattr(dependencies, "decode_access_token", _boom_decode)

    request = _make_request(f"Bearer {VALID_KEY}")
    principal = dependencies.get_principal(request, authorization=f"Bearer {VALID_KEY}")

    assert principal.subject == "user:22222222-2222-2222-2222-222222222222"
    assert captured["raw_key"] == VALID_KEY
    assert captured["client_ip"] == "203.0.113.10"
    assert request.state.auth_type == "user-api-key"
