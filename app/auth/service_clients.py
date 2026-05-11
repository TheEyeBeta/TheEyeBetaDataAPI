"""Service credential registry and validation."""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.scopes import has_required_scopes
from app.core.config import settings
from app.db.session import get_db_session
from app.domain.errors import AuthenticationError, AuthorizationError, DatabaseUnavailableError

logger = logging.getLogger("dataapi.auth")


@dataclass(frozen=True)
class ServiceClient:
    """Configured service client identity."""

    client_id: str
    scopes: list[str]
    secret: str | None = None
    client_uuid: str | None = None


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


def _get_service_client_from_env(client_id: str) -> ServiceClient:
    raw = settings.parsed_service_clients.get(client_id)
    if not raw:
        raise AuthenticationError("Unknown service client")
    scopes = raw.get("scopes")
    secret = str(raw.get("secret", ""))
    if not isinstance(scopes, list) or not secret:
        raise AuthenticationError("Invalid service client configuration")
    return ServiceClient(client_id=client_id, secret=secret, scopes=[str(scope) for scope in scopes])


def _get_service_client_from_db(client_id: str, session: Session) -> ServiceClient:
    row = (
        session.execute(
            text(
                """
                SELECT
                    c.client_uuid::text AS client_uuid,
                    c.client_id,
                    COALESCE(
                        array_agg(s.scope ORDER BY s.scope)
                        FILTER (WHERE s.scope IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS scopes
                FROM iam.service_clients c
                LEFT JOIN iam.service_client_scopes s
                  ON s.client_uuid = c.client_uuid
                WHERE c.client_id = :client_id
                  AND c.is_active = true
                  AND c.revoked_at IS NULL
                GROUP BY c.client_uuid, c.client_id
                """
            ),
            {"client_id": client_id},
        )
        .mappings()
        .first()
    )
    if not row:
        raise AuthenticationError("Unknown service client")

    raw_scopes = row.get("scopes") or []
    scopes = [str(scope).strip() for scope in raw_scopes if str(scope).strip()]
    return ServiceClient(
        client_id=str(row["client_id"]),
        client_uuid=str(row["client_uuid"]),
        scopes=scopes,
        secret=None,
    )


def get_service_client(client_id: str, session: Session | None = None) -> ServiceClient:
    mode = settings.service_client_auth_mode
    if mode == "environment":
        return _get_service_client_from_env(client_id)

    db_session, should_close = _acquire_session(session)
    try:
        return _get_service_client_from_db(client_id, db_session)
    except AuthenticationError:
        if mode == "hybrid":
            return _get_service_client_from_env(client_id)
        raise
    except SQLAlchemyError as exc:
        if mode == "hybrid":
            logger.warning("database-backed service auth unavailable, using environment fallback")
            return _get_service_client_from_env(client_id)
        raise DatabaseUnavailableError("Unable to verify service client registry") from exc
    finally:
        if should_close:
            db_session.close()


def _verify_service_client_secret_db(
    client: ServiceClient,
    provided_secret: str,
    session: Session | None,
    client_ip: str | None,
) -> None:
    if not client.client_uuid:
        raise AuthenticationError("Invalid service client configuration")

    db_session, should_close = _acquire_session(session)
    try:
        row = (
            db_session.execute(
                text(
                    """
                    SELECT secret_uuid::text AS secret_uuid
                    FROM iam.service_client_secrets
                    WHERE client_uuid = CAST(:client_uuid AS uuid)
                      AND is_active = true
                      AND revoked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > now())
                      AND secret_hash = crypt(:provided_secret, secret_hash)
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "client_uuid": client.client_uuid,
                    "provided_secret": provided_secret,
                },
            )
            .mappings()
            .first()
        )
        if not row:
            raise AuthenticationError("Invalid service credentials")

        normalized_ip = _normalize_client_ip(client_ip)
        if normalized_ip:
            db_session.execute(
                text(
                    """
                    UPDATE iam.service_client_secrets
                    SET last_used_at = now(),
                        last_used_ip = CAST(:client_ip AS inet)
                    WHERE secret_uuid = CAST(:secret_uuid AS uuid)
                    """
                ),
                {
                    "secret_uuid": str(row["secret_uuid"]),
                    "client_ip": normalized_ip,
                },
            )
        else:
            db_session.execute(
                text(
                    """
                    UPDATE iam.service_client_secrets
                    SET last_used_at = now()
                    WHERE secret_uuid = CAST(:secret_uuid AS uuid)
                    """
                ),
                {"secret_uuid": str(row["secret_uuid"])},
            )

        db_session.execute(
            text(
                """
                INSERT INTO iam.service_client_events (
                    client_uuid,
                    event_type,
                    actor_type,
                    actor_subject,
                    event_payload
                ) VALUES (
                    CAST(:client_uuid AS uuid),
                    'service_token_issued',
                    'service',
                    :actor_subject,
                    CAST(:event_payload AS jsonb)
                )
                """
            ),
            {
                "client_uuid": client.client_uuid,
                "actor_subject": f"service:{client.client_id}",
                "event_payload": json.dumps({"auth_mode": "database", "client_ip": normalized_ip or ""}),
            },
        )
        db_session.commit()
    except AuthenticationError:
        db_session.rollback()
        raise
    except SQLAlchemyError as exc:
        db_session.rollback()
        raise DatabaseUnavailableError("Unable to verify service credentials") from exc
    finally:
        if should_close:
            db_session.close()


def verify_service_client_secret(
    client: ServiceClient,
    provided_secret: str,
    *,
    session: Session | None = None,
    client_ip: str | None = None,
) -> None:
    if not provided_secret:
        raise AuthenticationError("Invalid service credentials")

    if client.secret is not None:
        if not hmac.compare_digest(client.secret, provided_secret):
            raise AuthenticationError("Invalid service credentials")
        return

    _verify_service_client_secret_db(
        client=client,
        provided_secret=provided_secret,
        session=session,
        client_ip=client_ip,
    )


def validate_requested_scopes(client: ServiceClient, requested_scopes: list[str]) -> list[str]:
    """Ensure requested scopes are subset of client-assigned scopes."""
    if not requested_scopes:
        return client.scopes
    if not has_required_scopes(client.scopes, requested_scopes):
        raise AuthorizationError("Requested scopes exceed service client grants")
    return requested_scopes


def validate_mtls_subject(client: ServiceClient, subject: str) -> None:
    """Validate that certificate subject matches configured service allowlist."""
    if not settings.service_mtls_enabled:
        raise AuthenticationError("mTLS authentication is not enabled")
    normalized_subject = subject.strip()
    if not normalized_subject:
        raise AuthenticationError("Missing certificate subject")

    allowed_subjects = settings.parsed_service_mtls_subjects.get(client.client_id, [])
    if not allowed_subjects:
        raise AuthenticationError("No mTLS subject allowlist configured for service client")
    if not any(hmac.compare_digest(allowed, normalized_subject) for allowed in allowed_subjects):
        raise AuthenticationError("Certificate subject is not allowed for this service client")
