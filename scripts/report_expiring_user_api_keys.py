#!/usr/bin/env python3
"""List active user API keys expiring within the next N days (default 30)."""

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

from app.db.session import get_db_session  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--within-days", type=int, default=30)
    args = parser.parse_args()
    if args.within_days < 1:
        raise SystemExit("--within-days must be >= 1")

    session = get_db_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT
                    k.key_uuid::text AS key_uuid,
                    k.key_prefix,
                    k.name,
                    u.email,
                    k.expires_at,
                    EXTRACT(EPOCH FROM (k.expires_at - now())) / 86400.0 AS days_remaining
                FROM iam.user_api_keys k
                JOIN iam.users u ON u.user_uuid = k.user_uuid
                WHERE k.is_active = true
                  AND k.revoked_at IS NULL
                  AND k.expires_at IS NOT NULL
                  AND k.expires_at > now()
                  AND k.expires_at <= now() + make_interval(days => :within_days)
                ORDER BY k.expires_at ASC
                """
            ),
            {"within_days": args.within_days},
        ).mappings().all()
        payload = [
            {
                "key_uuid": r["key_uuid"],
                "key_prefix": r["key_prefix"],
                "name": r["name"],
                "email": r["email"],
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                "days_remaining": float(r["days_remaining"]) if r["days_remaining"] is not None else None,
            }
            for r in rows
        ]
        print(json.dumps({"within_days": args.within_days, "count": len(payload), "keys": payload}, indent=2))
        return 0
    except SQLAlchemyError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
