"""Phase 3 refresh-token + short-lived opt-in tests (in-memory doubles)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.auth.service_clients import ServiceClient
from app.core.config import settings
from app.domain.errors import AuthenticationError
from app.repositories.sql_refresh_tokens import RefreshTokenRecord, hash_refresh_token
from app.services.auth_token_service import AuthTokenService


class _FakeRefreshRepo:
    """Test double — not real user/service data; clearly marked fake store."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def insert(self, *, subject, client_id, raw_token, scopes, expires_at):  # noqa: ANN001
        token_id = uuid4()
        self.rows[hash_refresh_token(raw_token)] = {
            "id": token_id,
            "subject": subject,
            "client_id": client_id,
            "scopes": list(scopes),
            "expires_at": expires_at,
            "revoked_at": None,
            "replaced_by": None,
        }
        return token_id

    def revoke_family(self, token_id) -> None:  # noqa: ANN001
        by_id = {row["id"]: row for row in self.rows.values()}
        current = by_id.get(token_id)
        while current is not None:
            if current["revoked_at"] is None:
                current["revoked_at"] = datetime.now(UTC)
            current = by_id.get(current["replaced_by"])

    def _reject_revoked(self, row: dict) -> None:
        if row["replaced_by"] is not None:
            self.revoke_family(row["id"])
        raise AuthenticationError("Refresh token already used or revoked")

    def lookup_active(self, presented_raw_token: str) -> RefreshTokenRecord:
        key = hash_refresh_token(presented_raw_token)
        row = self.rows.get(key)
        if not row:
            raise AuthenticationError("Invalid refresh token")
        if row["revoked_at"] is not None:
            self._reject_revoked(row)
        if row["expires_at"] <= datetime.now(UTC):
            raise AuthenticationError("Refresh token expired")
        return RefreshTokenRecord(
            id=row["id"],
            subject=row["subject"],
            client_id=row["client_id"],
            scopes=list(row["scopes"]),
            expires_at=row["expires_at"],
        )

    def revoke_active_for_client(self, client_id: str) -> None:
        for row in self.rows.values():
            if row["client_id"] == client_id and row["revoked_at"] is None:
                row["revoked_at"] = datetime.now(UTC)

    def rotate(  # noqa: ANN001
        self,
        *,
        presented_raw_token,
        new_raw_token,
        new_expires_at,
        scopes=None,
    ):
        key = hash_refresh_token(presented_raw_token)
        row = self.rows.get(key)
        if not row:
            raise AuthenticationError("Invalid refresh token")
        if row["revoked_at"] is not None:
            self._reject_revoked(row)
        if row["expires_at"] <= datetime.now(UTC):
            raise AuthenticationError("Refresh token expired")
        new_id = uuid4()
        new_key = hash_refresh_token(new_raw_token)
        new_scopes = list(scopes) if scopes is not None else list(row["scopes"])
        self.rows[new_key] = {
            "id": new_id,
            "subject": row["subject"],
            "client_id": row["client_id"],
            "scopes": new_scopes,
            "expires_at": new_expires_at,
            "revoked_at": None,
            "replaced_by": None,
        }
        row["revoked_at"] = datetime.now(UTC)
        row["replaced_by"] = new_id
        return RefreshTokenRecord(
            id=new_id,
            subject=row["subject"],
            client_id=row["client_id"],
            scopes=new_scopes,
            expires_at=new_expires_at,
        )


def _client(client_id: str = "vi-app", *, enabled: bool = True) -> ServiceClient:
    return ServiceClient(client_id=client_id, scopes=["market:read"], short_lived_tokens_enabled=enabled)


def _seed(
    fake: _FakeRefreshRepo, raw: str, *, client_id: str = "vi-app", subject: str | None = None, days: int = 1
) -> None:
    fake.insert(
        subject=subject or f"service:{client_id}",
        client_id=client_id,
        raw_token=raw,
        scopes=["market:read"],
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )


def _patch_repo(monkeypatch: pytest.MonkeyPatch, fake: _FakeRefreshRepo) -> None:
    monkeypatch.setattr(
        "app.services.auth_token_service.RefreshTokenRepository",
        lambda session: fake,
    )


def test_opted_out_client_keeps_long_lived_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ServiceClient(
        client_id="vi-app",
        scopes=["market:read"],
        short_lived_tokens_enabled=False,
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    monkeypatch.setattr(
        "app.services.auth_token_service.RefreshTokenRepository",
        lambda session: (_ for _ in ()).throw(AssertionError("repo must not be used")),
    )
    result = service.issue_service_token(client, ["market:read"])
    assert result.refresh_token is None
    assert result.expires_minutes == settings.service_token_expires_minutes


def test_opted_in_client_gets_short_lived_and_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    client = ServiceClient(
        client_id="vi-app",
        scopes=["market:read", "advisor:read"],
        short_lived_tokens_enabled=True,
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    issued = service.issue_service_token(client, ["market:read"])
    assert issued.refresh_token
    assert issued.expires_minutes == settings.short_lived_access_token_minutes
    assert len(fake.rows) == 1

    refreshed = service.refresh(issued.refresh_token, client)
    assert refreshed.refresh_token != issued.refresh_token
    assert refreshed.access_token
    assert refreshed.expires_minutes == settings.short_lived_access_token_minutes
    assert refreshed.scopes == ["market:read"]

    with pytest.raises(AuthenticationError, match="already used|revoked"):
        service.refresh(issued.refresh_token, client)


def test_refresh_intersects_live_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    raw = "test-refresh-token-value-xxxxxxxx"
    fake.insert(
        subject="service:vi-app",
        client_id="vi-app",
        raw_token=raw,
        scopes=["market:read", "advisor:read"],
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    live = ServiceClient(
        client_id="vi-app",
        scopes=["market:read"],  # advisor:read removed
        short_lived_tokens_enabled=True,
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    refreshed = service.refresh(raw, live)
    assert refreshed.scopes == ["market:read"]


def test_refresh_rejects_when_short_lived_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    raw = "test-refresh-token-value-yyyyyyyy"
    fake.insert(
        subject="service:vi-app",
        client_id="vi-app",
        raw_token=raw,
        scopes=["market:read"],
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    live = ServiceClient(
        client_id="vi-app",
        scopes=["market:read"],
        short_lived_tokens_enabled=False,
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError, match="disabled"):
        service.refresh(raw, live)
    assert fake.rows[hash_refresh_token(raw)]["revoked_at"] is not None


def test_revoked_refresh_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    raw = "test-refresh-token-value-zzzzzzzz"
    fake.insert(
        subject="service:vi-app",
        client_id="vi-app",
        raw_token=raw,
        scopes=["market:read"],
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    fake.rows[hash_refresh_token(raw)]["revoked_at"] = datetime.now(UTC)
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError):
        service.refresh(raw, _client())


# ---------------------------------------------------------------------------
# Family / binding semantics (the SQL repository is exercised the same way in
# tests/integration/test_iam_postgres.py).
# ---------------------------------------------------------------------------


def test_reuse_of_rotated_token_revokes_whole_family(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    first = "family-token-0000000000000000"
    _seed(fake, first)
    second = service.refresh(first, _client()).refresh_token
    third = service.refresh(second, _client()).refresh_token

    with pytest.raises(AuthenticationError, match="already used"):
        service.refresh(first, _client())  # replay of the oldest token

    assert all(row["revoked_at"] is not None for row in fake.rows.values())
    with pytest.raises(AuthenticationError):
        service.refresh(third, _client())  # legitimate holder is cut off too


def test_explicitly_revoked_token_does_not_touch_other_families(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    revoked, other = "revoked-token-000000000000000", "other-token-00000000000000000"
    _seed(fake, revoked)
    _seed(fake, other)
    fake.rows[hash_refresh_token(revoked)]["revoked_at"] = datetime.now(UTC)
    with pytest.raises(AuthenticationError, match="already used or revoked"):
        service.refresh(revoked, _client())
    assert service.refresh(other, _client()).refresh_token


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    raw = "expired-token-000000000000000"
    _seed(fake, raw, days=-1)
    with pytest.raises(AuthenticationError, match="expired"):
        AuthTokenService(session=object()).refresh(raw, _client())  # type: ignore[arg-type]


def test_token_presented_by_another_client_is_rejected_and_family_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    raw = "client-bound-token-0000000000"
    _seed(fake, raw, client_id="vi-app")
    with pytest.raises(AuthenticationError, match="^Invalid refresh token$"):
        AuthTokenService(session=object()).refresh(raw, _client("other-client"))  # type: ignore[arg-type]
    assert fake.rows[hash_refresh_token(raw)]["revoked_at"] is not None


def test_token_with_foreign_subject_is_rejected_and_family_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRefreshRepo()
    _patch_repo(monkeypatch, fake)
    raw = "subject-bound-token-000000000"
    _seed(fake, raw, client_id="vi-app", subject="user:someone-else")
    with pytest.raises(AuthenticationError, match="^Invalid refresh token$"):
        AuthTokenService(session=object()).refresh(raw, _client())  # type: ignore[arg-type]
    assert fake.rows[hash_refresh_token(raw)]["revoked_at"] is not None


def test_refresh_route_requires_client_credentials() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).post("/api/v1/auth/refresh", json={"refresh_token": "x" * 32})
    assert response.status_code == 401
