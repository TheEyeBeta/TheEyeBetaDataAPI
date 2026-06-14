#!/usr/bin/env python3
"""Provision an end-user and issue a personal API key.

Mirrors scripts/provision_db_service_client.py but for human end-users in
iam.users / iam.user_api_keys. The raw key is printed exactly once; only its
bcrypt hash is stored.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.session import get_db_session

DEFAULT_SCOPES = ["market:read", "symbols:read"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision an end-user and issue a personal API key.")
    parser.add_argument("--email", required=True, help="User email (used as the unique identity).")
    parser.add_argument("--display-name", default="", help="Human-readable user name.")
    parser.add_argument("--key-name", default="", help="Label for the issued key (e.g. 'Trading bot').")
    parser.add_argument(
        "--plan",
        default="free",
        choices=["free", "starter", "pro", "enterprise"],
        help="User plan tier (applied on first creation).",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help=f"Scope grant for the key. May be repeated. Defaults to {DEFAULT_SCOPES}.",
    )
    parser.add_argument("--created-by", default="local-admin", help="Actor recorded in the audit trail.")
    parser.add_argument(
        "--expires-days",
        type=int,
        default=0,
        help="Optional key expiry in days (0 means no expiry).",
    )
    return parser.parse_args()


def _normalize_scopes(values: list[str]) -> list[str]:
    normalized = [value.strip() for value in values if value and value.strip()]
    if not normalized:
        return list(DEFAULT_SCOPES)
    return sorted(set(normalized))


def _expires_at(days: int) -> datetime | None:
    if days <= 0:
        return None
    return datetime.now(UTC) + timedelta(days=days)


def main() -> int:
    args = _parse_args()
    scopes = _normalize_scopes(args.scope)
    expires_at = _expires_at(args.expires_days)
    session = get_db_session()
    try:
        issued = (
            session.execute(
                text(
                    """
                    SELECT user_uuid::text AS user_uuid,
                           email,
                           key_uuid::text AS key_uuid,
                           key_prefix,
                           api_key,
                           scopes,
                           expires_at
                    FROM iam.provision_user_api_key(
                        :email,
                        :display_name,
                        :key_name,
                        CAST(:scopes AS text[]),
                        :created_by,
                        :plan,
                        :expires_at
                    )
                    """
                ),
                {
                    "email": args.email,
                    "display_name": args.display_name,
                    "key_name": args.key_name,
                    "scopes": scopes,
                    "created_by": args.created_by,
                    "plan": args.plan,
                    "expires_at": expires_at,
                },
            )
            .mappings()
            .one()
        )
        session.commit()
    except (SQLAlchemyError, ValueError) as exc:
        session.rollback()
        raise SystemExit(str(exc)) from exc
    finally:
        session.close()

    print(
        json.dumps(
            {
                "user_uuid": str(issued["user_uuid"]),
                "email": str(issued["email"]),
                "key_uuid": str(issued["key_uuid"]),
                "key_prefix": str(issued["key_prefix"]),
                "api_key": str(issued["api_key"]),
                "scopes": list(issued["scopes"]),
                "expires_at": issued["expires_at"].isoformat() if issued["expires_at"] else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
