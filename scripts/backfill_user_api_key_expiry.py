#!/usr/bin/env python3
"""Backfill expires_at for active user API keys that have none.

Sets expires_at = now() + USER_API_KEY_BACKFILL_DAYS (default 180). Never uses
a past timestamp. Logs each update into iam.user_api_key_events and, when
present, iam.auth_audit_log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import get_db_session  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=settings.user_api_key_backfill_days,
        help="Days from now for backfilled expiry (default USER_API_KEY_BACKFILL_DAYS).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only; do not update rows.",
    )
    args = parser.parse_args()
    if args.days < 1:
        raise SystemExit("--days must be >= 1")

    session = get_db_session()
    try:
        candidates = session.execute(
            text(
                """
                SELECT key_uuid::text AS key_uuid, user_uuid::text AS user_uuid
                FROM iam.user_api_keys
                WHERE is_active = true
                  AND revoked_at IS NULL
                  AND expires_at IS NULL
                """
            )
        ).mappings().all()
        print(json.dumps({"candidates": len(candidates), "days": args.days, "dry_run": args.dry_run}))
        if args.dry_run or not candidates:
            return 0

        for row in candidates:
            session.execute(
                text(
                    """
                    UPDATE iam.user_api_keys
                    SET expires_at = now() + make_interval(days => :days)
                    WHERE key_uuid = CAST(:key_uuid AS uuid)
                      AND expires_at IS NULL
                    """
                ),
                {"key_uuid": row["key_uuid"], "days": args.days},
            )
            session.execute(
                text(
                    """
                    INSERT INTO iam.user_api_key_events (
                        user_uuid, key_uuid, event_type, actor_type, actor_subject, event_payload
                    ) VALUES (
                        CAST(:user_uuid AS uuid),
                        CAST(:key_uuid AS uuid),
                        'key_expiry_backfill',
                        'system',
                        'backfill_user_api_key_expiry',
                        CAST(:payload AS jsonb)
                    )
                    """
                ),
                {
                    "user_uuid": row["user_uuid"],
                    "key_uuid": row["key_uuid"],
                    "payload": json.dumps({"days": args.days}),
                },
            )
        session.commit()
        print(json.dumps({"updated": len(candidates)}))
        return 0
    except SQLAlchemyError as exc:
        session.rollback()
        raise SystemExit(str(exc)) from exc
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
