#!/usr/bin/env python3
"""Provision or update a DB-backed service client credential."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.session import get_db_session


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision DB-backed service client credentials.")
    parser.add_argument("--client-id", required=True, help="Unique service client ID.")
    parser.add_argument("--display-name", required=True, help="Human-readable service name.")
    parser.add_argument("--app-type", required=True, help="App type from iam.client_types.")
    parser.add_argument(
        "--environment",
        default="production",
        choices=["development", "staging", "production"],
        help="Service environment label.",
    )
    parser.add_argument(
        "--created-by",
        default="local-admin",
        help="Actor recorded in audit trail.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Additional scope grant. May be repeated.",
    )
    parser.add_argument(
        "--secret",
        default="",
        help="Optional explicit API key secret to store. If omitted, DB generates one.",
    )
    parser.add_argument(
        "--expires-days",
        type=int,
        default=0,
        help="Optional secret expiry in days (0 means no expiry).",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow updating an existing client.",
    )
    parser.add_argument(
        "--keep-existing-secrets",
        action="store_true",
        help="Do not deactivate existing active secrets before issuing a new one.",
    )
    return parser.parse_args()


def _normalize_scopes(values: list[str]) -> list[str]:
    normalized = [value.strip() for value in values if value and value.strip()]
    # Keep deterministic ordering and uniqueness.
    return sorted(set(normalized))


def _expires_at(days: int) -> datetime | None:
    if days <= 0:
        return None
    return datetime.now(UTC) + timedelta(days=days)


def _upsert_client(session, args: argparse.Namespace) -> str:
    existing = (
        session.execute(
            text(
                """
                SELECT client_uuid::text AS client_uuid
                FROM iam.service_clients
                WHERE client_id = :client_id
                """
            ),
            {"client_id": args.client_id},
        )
        .mappings()
        .first()
    )
    if existing:
        if not args.allow_existing:
            raise ValueError(f"Client already exists: {args.client_id}. Re-run with --allow-existing.")
        session.execute(
            text(
                """
                UPDATE iam.service_clients
                SET
                    display_name = :display_name,
                    app_type = :app_type,
                    environment = :environment,
                    is_active = true,
                    revoked_at = NULL,
                    revoked_reason = NULL,
                    updated_by = :updated_by
                WHERE client_uuid = CAST(:client_uuid AS uuid)
                """
            ),
            {
                "display_name": args.display_name,
                "app_type": args.app_type,
                "environment": args.environment,
                "updated_by": args.created_by,
                "client_uuid": existing["client_uuid"],
            },
        )
        return str(existing["client_uuid"])

    created = (
        session.execute(
            text(
                """
                INSERT INTO iam.service_clients (
                    client_id,
                    display_name,
                    app_type,
                    environment,
                    metadata,
                    created_by,
                    updated_by
                ) VALUES (
                    :client_id,
                    :display_name,
                    :app_type,
                    :environment,
                    '{}'::jsonb,
                    :created_by,
                    :created_by
                )
                RETURNING client_uuid::text AS client_uuid
                """
            ),
            {
                "client_id": args.client_id,
                "display_name": args.display_name,
                "app_type": args.app_type,
                "environment": args.environment,
                "created_by": args.created_by,
            },
        )
        .mappings()
        .one()
    )
    return str(created["client_uuid"])


def _grant_manual_scopes(session, client_uuid: str, scopes: list[str], created_by: str) -> None:
    for scope in scopes:
        session.execute(
            text(
                """
                INSERT INTO iam.service_client_scopes (
                    client_uuid,
                    scope,
                    grant_source,
                    granted_by
                ) VALUES (
                    CAST(:client_uuid AS uuid),
                    :scope,
                    'manual',
                    :granted_by
                )
                ON CONFLICT (client_uuid, scope) DO NOTHING
                """
            ),
            {
                "client_uuid": client_uuid,
                "scope": scope,
                "granted_by": created_by,
            },
        )


def _deactivate_existing_secrets(session, client_uuid: str, created_by: str) -> None:
    session.execute(
        text(
            """
            UPDATE iam.service_client_secrets
            SET
                is_active = false,
                revoked_at = COALESCE(revoked_at, now()),
                revoked_reason = COALESCE(revoked_reason, 'rotated'),
                metadata = jsonb_set(
                    COALESCE(metadata, '{}'::jsonb),
                    '{rotated_by}',
                    to_jsonb(CAST(:rotated_by AS text)),
                    true
                )
            WHERE client_uuid = CAST(:client_uuid AS uuid)
              AND is_active = true
            """
        ),
        {
            "client_uuid": client_uuid,
            "rotated_by": created_by,
        },
    )


def _issue_secret(session, args: argparse.Namespace, client_uuid: str, expires_at: datetime | None) -> tuple[str, str]:
    if args.secret.strip():
        secret = args.secret.strip()
        prefix = secrets.token_hex(4)
        session.execute(
            text(
                """
                INSERT INTO iam.service_client_secrets (
                    client_uuid,
                    secret_prefix,
                    secret_hash,
                    hash_algorithm,
                    created_by,
                    expires_at
                ) VALUES (
                    CAST(:client_uuid AS uuid),
                    :secret_prefix,
                    crypt(:secret, gen_salt('bf', 12)),
                    'bcrypt',
                    :created_by,
                    :expires_at
                )
                """
            ),
            {
                "client_uuid": client_uuid,
                "secret_prefix": prefix,
                "secret": secret,
                "created_by": args.created_by,
                "expires_at": expires_at,
            },
        )
        return secret, prefix

    issued = (
        session.execute(
            text(
                """
                SELECT secret_prefix, api_key
                FROM iam.issue_service_api_key(
                    :client_id,
                    :created_by,
                    :expires_at
                )
                """
            ),
            {
                "client_id": args.client_id,
                "created_by": args.created_by,
                "expires_at": expires_at,
            },
        )
        .mappings()
        .one()
    )
    return str(issued["api_key"]), str(issued["secret_prefix"])


def _fetch_scopes(session, client_uuid: str) -> list[str]:
    rows = (
        session.execute(
            text(
                """
                SELECT scope
                FROM iam.service_client_scopes
                WHERE client_uuid = CAST(:client_uuid AS uuid)
                ORDER BY scope
                """
            ),
            {"client_uuid": client_uuid},
        )
        .mappings()
        .all()
    )
    return [str(row["scope"]) for row in rows]


def main() -> int:
    args = _parse_args()
    manual_scopes = _normalize_scopes(args.scope)
    expires_at = _expires_at(args.expires_days)
    session = get_db_session()
    try:
        client_uuid = _upsert_client(session, args)
        _grant_manual_scopes(session, client_uuid, manual_scopes, args.created_by)
        if not args.keep_existing_secrets:
            _deactivate_existing_secrets(session, client_uuid, args.created_by)
        secret, prefix = _issue_secret(session, args, client_uuid, expires_at)
        scopes = _fetch_scopes(session, client_uuid)
        session.commit()
    except (SQLAlchemyError, ValueError) as exc:
        session.rollback()
        raise SystemExit(str(exc)) from exc
    finally:
        session.close()

    print(
        json.dumps(
            {
                "client_id": args.client_id,
                "client_uuid": client_uuid,
                "secret_prefix": prefix,
                "secret": secret,
                "scopes": scopes,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
