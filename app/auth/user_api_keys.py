"""End-user API key validation.

Personal keys are opaque bearer tokens shaped ``teb_uk_<16hex>_<secret>``. We
look the key up by its globally unique prefix and verify it with pgcrypto's
``crypt(:raw_key, key_hash)`` — passing the stored hash back in as the salt so
the comparison is deterministic. (Hashing the incoming key with a fresh
``gen_salt`` and matching on equality would never match, since bcrypt embeds a
random salt per call.) Heavy bcrypt work happens in PostgreSQL on a prefix-
indexed single row, so each request costs one indexed lookup, not a table scan.
"""

from __future__ import annotations

import ipaddress
import json
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.models import Principal, PrincipalType
from app.db.session import get_db_session
from app.domain.errors import AuthenticationError, DatabaseUnavailableError

logger = logging.getLogger("dataapi.auth")

USER_API_KEY_PREFIX = "teb_uk_"
# 8 random bytes rendered as hex (see iam.issue_user_api_key).
_PREFIX_HEX_LEN = 16


def is_user_api_key(token: str) -> bool:
    """Return True if the bearer token looks like a personal API key."""
    return token.startswith(USER_API_KEY_PREFIX)


def _extract_key_prefix(raw_key: str) -> str:
    """Pull the fixed-length lookup prefix out of a raw key.

    The secret segment may contain underscores (base64url), so we read a fixed
    window rather than splitting on ``_``.
    """
    if not raw_key.startswith(USER_API_KEY_PREFIX):
        raise AuthenticationError("Invalid API key")
    body = raw_key[len(USER_API_KEY_PREFIX):]
    prefix = body[:_PREFIX_HEX_LEN]
    # Must be 16 hex chars followed by '_' and a non-empty secret.
    if len(prefix) != _PREFIX_HEX_LEN or body[_PREFIX_HEX_LEN:_PREFIX_HEX_LEN + 1] != "_":
        raise AuthenticationError("Invalid API key")
    if len(body) <= _PREFIX_HEX_LEN + 1:
        raise AuthenticationError("Invalid API key")
    try:
        int(prefix, 16)
    except ValueError as exc:
        raise AuthenticationError("Invalid API key") from exc
    return prefix


def _normalize_client_ip(client_ip: str | None) -> str | None:
    if not client_ip:
        return None
    candidate = client_ip.strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _acquire_session(session: Session | None) -> tuple[Session, bool]:
    if session is not None:
        return session, False
    return get_db_session(), True


def _log_event(
    session: Session,
    *,
    user_uuid: str | None,
    key_uuid: str | None,
    event_type: str,
    actor_subject: str,
    payload: dict,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO iam.user_api_key_events (
                user_uuid,
                key_uuid,
                event_type,
                actor_type,
                actor_subject,
                event_payload
            ) VALUES (
                CAST(:user_uuid AS uuid),
                CAST(:key_uuid AS uuid),
                :event_type,
                'user',
                :actor_subject,
                CAST(:event_payload AS jsonb)
            )
            """
        ),
        {
            "user_uuid": user_uuid,
            "key_uuid": key_uuid,
            "event_type": event_type,
            "actor_subject": actor_subject,
            "event_payload": json.dumps(payload),
        },
    )


def verify_user_api_key(
    raw_key: str,
    *,
    session: Session | None = None,
    client_ip: str | None = None,
) -> Principal:
    """Validate a personal API key and return the authenticated principal.

    Raises AuthenticationError for any invalid/revoked/expired key. The caller
    is never told *why* a key failed (all paths return "Invalid API key"); the
    specific reason is recorded in iam.user_api_key_events instead.
    """
    prefix = _extract_key_prefix(raw_key)
    normalized_ip = _normalize_client_ip(client_ip)
    db_session, should_close = _acquire_session(session)
    try:
        row = (
            db_session.execute(
                text(
                    """
                    SELECT
                        k.key_uuid::text AS key_uuid,
                        k.user_uuid::text AS user_uuid,
                        k.scopes AS scopes,
                        (k.is_active AND k.revoked_at IS NULL) AS key_enabled,
                        (k.expires_at IS NOT NULL AND k.expires_at <= now()) AS is_expired,
                        u.is_active AS user_active
                    FROM iam.user_api_keys k
                    JOIN iam.users u ON u.user_uuid = k.user_uuid
                    WHERE k.key_prefix = :prefix
                      AND k.key_hash = crypt(:raw_key, k.key_hash)
                    LIMIT 1
                    """
                ),
                {"prefix": prefix, "raw_key": raw_key},
            )
            .mappings()
            .first()
        )

        failure_reason: str | None = None
        if not row:
            failure_reason = "invalid_key"
        elif not row["key_enabled"]:
            failure_reason = "key_revoked"
        elif row["is_expired"]:
            failure_reason = "key_expired"
        elif not row["user_active"]:
            failure_reason = "user_inactive"

        if failure_reason is not None:
            _log_event(
                db_session,
                user_uuid=row["user_uuid"] if row else None,
                key_uuid=row["key_uuid"] if row else None,
                event_type="key_rejected",
                actor_subject=f"prefix:{prefix}",
                payload={"reason": failure_reason, "client_ip": normalized_ip or ""},
            )
            db_session.commit()
            raise AuthenticationError("Invalid API key")

        scopes = [str(scope).strip() for scope in (row["scopes"] or []) if str(scope).strip()]

        if normalized_ip:
            db_session.execute(
                text(
                    """
                    UPDATE iam.user_api_keys
                    SET last_used_at = now(), last_used_ip = CAST(:client_ip AS inet)
                    WHERE key_uuid = CAST(:key_uuid AS uuid)
                    """
                ),
                {"client_ip": normalized_ip, "key_uuid": row["key_uuid"]},
            )
        else:
            db_session.execute(
                text(
                    """
                    UPDATE iam.user_api_keys
                    SET last_used_at = now()
                    WHERE key_uuid = CAST(:key_uuid AS uuid)
                    """
                ),
                {"key_uuid": row["key_uuid"]},
            )

        db_session.commit()
        return Principal(
            subject=f"user:{row['user_uuid']}",
            principal_type=PrincipalType.USER,
            scopes=frozenset(scopes),
            client_id=None,
        )
    except AuthenticationError:
        db_session.rollback()
        raise
    except SQLAlchemyError as exc:
        db_session.rollback()
        raise DatabaseUnavailableError("Unable to verify API key") from exc
    finally:
        if should_close:
            db_session.close()
