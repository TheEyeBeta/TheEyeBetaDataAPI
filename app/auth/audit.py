"""Best-effort writes to iam.auth_audit_log (never fails the request path)."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session

logger = logging.getLogger("dataapi.auth.audit")


def record_auth_audit(
    *,
    subject: str | None,
    scope_required: str | None,
    scope_granted: str | None,
    route: str | None,
    outcome: str,
) -> None:
    """Insert an auth audit row. Swallows DB errors so authz remains authoritative."""
    session = get_db_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO iam.auth_audit_log (
                    subject, scope_required, scope_granted, route, outcome
                )
                VALUES (
                    :subject, :scope_required, :scope_granted, :route, :outcome
                )
                """
            ),
            {
                "subject": subject,
                "scope_required": scope_required,
                "scope_granted": scope_granted,
                "route": route,
                "outcome": outcome,
            },
        )
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.warning("auth_audit_log write failed: %s", exc)
    finally:
        session.close()
