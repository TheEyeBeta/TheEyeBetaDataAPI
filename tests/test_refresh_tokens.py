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

    def lookup_active(self, presented_raw_token: str) -> RefreshTokenRecord:
        key = hash_refresh_token(presented_raw_token)
        row = self.rows.get(key)
        if not row:
            raise AuthenticationError("Invalid refresh token")
        if row["revoked_at"] is not None:
            raise AuthenticationError("Refresh token already used or revoked")
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
            raise AuthenticationError("Refresh token already used or revoked")
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
    monkeypatch.setattr(
        "app.services.auth_token_service.get_service_client",
        lambda client_id, session=None: client,
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    issued = service.issue_service_token(client, ["market:read"])
    assert issued.refresh_token
    assert issued.expires_minutes == settings.short_lived_access_token_minutes
    assert len(fake.rows) == 1

    refreshed = service.refresh(issued.refresh_token)
    assert refreshed.refresh_token != issued.refresh_token
    assert refreshed.access_token
    assert refreshed.expires_minutes == settings.short_lived_access_token_minutes
    assert refreshed.scopes == ["market:read"]

    with pytest.raises(AuthenticationError, match="already used|revoked"):
        service.refresh(issued.refresh_token)


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
    monkeypatch.setattr(
        "app.services.auth_token_service.get_service_client",
        lambda client_id, session=None: live,
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    refreshed = service.refresh(raw)
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
    monkeypatch.setattr(
        "app.services.auth_token_service.get_service_client",
        lambda client_id, session=None: live,
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError, match="disabled"):
        service.refresh(raw)
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
    monkeypatch.setattr(
        "app.services.auth_token_service.get_service_client",
        lambda client_id, session=None: ServiceClient(
            client_id="vi-app",
            scopes=["market:read"],
            short_lived_tokens_enabled=True,
        ),
    )
    service = AuthTokenService(session=object())  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError):
        service.refresh(raw)
