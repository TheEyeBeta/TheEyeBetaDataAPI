"""Refresh-token persistence (SHA-256 hashes only — never raw tokens)."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.errors import AuthenticationError, DatabaseUnavailableError


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def mint_refresh_token_value() -> str:
    return secrets.token_urlsafe(48)


@dataclass(frozen=True)
class RefreshTokenRecord:
    id: UUID
    subject: str
    client_id: str
    scopes: list[str]
    expires_at: datetime


class RefreshTokenRepository:
    """SQL repository for iam.refresh_tokens."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(
        self,
        *,
        subject: str,
        client_id: str,
        raw_token: str,
        scopes: list[str],
        expires_at: datetime,
    ) -> UUID:
        token_hash = hash_refresh_token(raw_token)
        try:
            row = self._session.execute(
                text(
                    """
                    INSERT INTO iam.refresh_tokens (
                        subject, client_id, token_hash, expires_at, metadata
                    )
                    VALUES (
                        :subject, :client_id, :token_hash, :expires_at,
                        jsonb_build_object('scopes', CAST(:scopes AS jsonb))
                    )
                    RETURNING id
                    """
                ),
                {
                    "subject": subject,
                    "client_id": client_id,
                    "token_hash": token_hash,
                    "expires_at": expires_at,
                    "scopes": json.dumps(scopes),
                },
            ).scalar_one()
            self._session.commit()
            return UUID(str(row))
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise DatabaseUnavailableError("Unable to persist refresh token") from exc

    def lookup_active(self, presented_raw_token: str) -> RefreshTokenRecord:
        """Return an active, unexpired refresh row (no mutation)."""
        presented_hash = hash_refresh_token(presented_raw_token)
        try:
            row = (
                self._session.execute(
                    text(
                        """
                        SELECT id, subject, client_id, expires_at, revoked_at,
                               metadata -> 'scopes' AS scopes
                        FROM iam.refresh_tokens
                        WHERE token_hash = :token_hash
                        """
                    ),
                    {"token_hash": presented_hash},
                )
                .mappings()
                .first()
            )
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError("Unable to look up refresh token") from exc
        if not row:
            raise AuthenticationError("Invalid refresh token")
        if row["revoked_at"] is not None:
            raise AuthenticationError("Refresh token already used or revoked")
        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise AuthenticationError("Refresh token expired")
        raw_scopes = row.get("scopes") or []
        if isinstance(raw_scopes, str):
            raw_scopes = json.loads(raw_scopes)
        return RefreshTokenRecord(
            id=UUID(str(row["id"])),
            subject=str(row["subject"]),
            client_id=str(row["client_id"]),
            scopes=[str(s) for s in raw_scopes],
            expires_at=expires_at,
        )

    def revoke_active_for_client(self, client_id: str) -> None:
        """Revoke all active refresh tokens for a client (authz change / disable)."""
        try:
            self._session.execute(
                text(
                    """
                    UPDATE iam.refresh_tokens
                    SET revoked_at = now()
                    WHERE client_id = :client_id
                      AND revoked_at IS NULL
                    """
                ),
                {"client_id": client_id},
            )
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise DatabaseUnavailableError("Unable to revoke refresh tokens") from exc

    def rotate(
        self,
        *,
        presented_raw_token: str,
        new_raw_token: str,
        new_expires_at: datetime,
        scopes: list[str] | None = None,
    ) -> RefreshTokenRecord:
        """Validate + revoke the presented token; insert a replacement (rotate-on-use).

        When ``scopes`` is provided, the replacement stores that list (current
        intersection). Otherwise the previous snapshot is copied.
        """
        presented_hash = hash_refresh_token(presented_raw_token)
        new_hash = hash_refresh_token(new_raw_token)
        try:
            row = (
                self._session.execute(
                    text(
                        """
                        SELECT id, subject, client_id, expires_at, revoked_at,
                               metadata -> 'scopes' AS scopes
                        FROM iam.refresh_tokens
                        WHERE token_hash = :token_hash
                        FOR UPDATE
                        """
                    ),
                    {"token_hash": presented_hash},
                )
                .mappings()
                .first()
            )
            if not row:
                raise AuthenticationError("Invalid refresh token")
            if row["revoked_at"] is not None:
                raise AuthenticationError("Refresh token already used or revoked")
            expires_at = row["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                raise AuthenticationError("Refresh token expired")

            if scopes is None:
                raw_scopes = row.get("scopes") or []
                if isinstance(raw_scopes, str):
                    raw_scopes = json.loads(raw_scopes)
                scopes = [str(s) for s in raw_scopes]
            else:
                scopes = [str(s) for s in scopes]

            new_id = self._session.execute(
                text(
                    """
                    INSERT INTO iam.refresh_tokens (
                        subject, client_id, token_hash, expires_at, metadata
                    )
                    VALUES (
                        :subject, :client_id, :token_hash, :expires_at,
                        jsonb_build_object('scopes', CAST(:scopes AS jsonb))
                    )
                    RETURNING id
                    """
                ),
                {
                    "subject": row["subject"],
                    "client_id": row["client_id"],
                    "token_hash": new_hash,
                    "expires_at": new_expires_at,
                    "scopes": json.dumps(scopes),
                },
            ).scalar_one()

            self._session.execute(
                text(
                    """
                    UPDATE iam.refresh_tokens
                    SET revoked_at = now(),
                        replaced_by = CAST(:new_id AS uuid)
                    WHERE id = CAST(:old_id AS uuid)
                    """
                ),
                {"new_id": str(new_id), "old_id": str(row["id"])},
            )
            self._session.commit()
            return RefreshTokenRecord(
                id=UUID(str(new_id)),
                subject=str(row["subject"]),
                client_id=str(row["client_id"]),
                scopes=scopes,
                expires_at=new_expires_at,
            )
        except AuthenticationError:
            self._session.rollback()
            raise
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise DatabaseUnavailableError("Unable to rotate refresh token") from exc
