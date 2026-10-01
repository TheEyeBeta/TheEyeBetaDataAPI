"""Refresh-token persistence (SHA-256 hashes only — never raw tokens).

Rotate-on-use. Each rotation links old -> new through ``replaced_by``, so a
chain of rows is one token *family*. Presenting a token that was already
rotated is treated as theft (RFC 9700 section 4.14.2): every descendant in its
family is revoked, so whichever party holds the newest token is cut off too.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.errors import AuthenticationError, DatabaseUnavailableError

logger = logging.getLogger("dataapi.auth")

# Descendants of one row (the row itself included), following replaced_by.
_FAMILY_REVOKE_SQL = text(
    """
    WITH RECURSIVE family AS (
        SELECT id, replaced_by FROM iam.refresh_tokens WHERE id = CAST(:id AS uuid)
        UNION
        SELECT t.id, t.replaced_by
        FROM iam.refresh_tokens t
        JOIN family f ON t.id = f.replaced_by
    )
    UPDATE iam.refresh_tokens
    SET revoked_at = now()
    WHERE id IN (SELECT id FROM family)
      AND revoked_at IS NULL
    """
)


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
                        SELECT id, subject, client_id, expires_at, revoked_at, replaced_by,
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
            self._reject_revoked(row)
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

    def revoke_family(self, token_id: UUID) -> None:
        """Revoke ``token_id`` and every token rotated from it; commits."""
        try:
            self._session.execute(_FAMILY_REVOKE_SQL, {"id": str(token_id)})
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise DatabaseUnavailableError("Unable to revoke refresh token family") from exc

    def _reject_revoked(self, row) -> None:  # noqa: ANN001 - SQLAlchemy RowMapping
        """Raise for a revoked row; a rotated one (reuse) first revokes its family."""
        if row["replaced_by"] is not None:
            logger.warning(
                "refresh token reuse detected; revoking token family",
                extra={"client_id": str(row["client_id"]), "refresh_token_id": str(row["id"])},
            )
            self.revoke_family(UUID(str(row["id"])))
        raise AuthenticationError("Refresh token already used or revoked")

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
                        SELECT id, subject, client_id, expires_at, revoked_at, replaced_by,
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
                # Also the loser of two concurrent rotations of one token: it
                # waited on FOR UPDATE and now sees the winner's revocation.
                self._reject_revoked(row)
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
