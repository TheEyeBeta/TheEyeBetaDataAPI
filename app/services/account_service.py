"""Admin account lifecycle: create and deactivate end-user accounts.

Deletion is a soft-delete (``iam.users.is_active = false``): the existing
``iam.revoke_user_keys_on_disable`` trigger auto-revokes the account's API
keys and logs a ``user_disabled`` event when that flag flips. We additionally
record the admin-initiated event ourselves so the approval-code check and the
acting operator are attributable in ``iam.user_api_key_events``.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.account_approval import require_account_approval
from app.domain.errors import ConflictAppError, DatabaseUnavailableError, NotFoundAppError

logger = logging.getLogger("dataapi.audit")


class AccountService:
    """Create and deactivate iam.users rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_account(
        self,
        *,
        email: str,
        display_name: str | None,
        organization: str | None,
        plan: str,
        actor_subject: str,
    ) -> dict:
        try:
            row = (
                self._session.execute(
                    text(
                        """
                        INSERT INTO iam.users (email, display_name, organization, plan, created_by)
                        VALUES (lower(:email), :display_name, :organization, :plan, :actor_subject)
                        RETURNING
                            user_uuid::text AS user_uuid,
                            email,
                            display_name,
                            organization,
                            plan,
                            is_active,
                            created_at
                        """
                    ),
                    {
                        "email": email,
                        "display_name": display_name,
                        "organization": organization,
                        "plan": plan,
                        "actor_subject": actor_subject,
                    },
                )
                .mappings()
                .first()
            )
            self._log_event(
                user_uuid=row["user_uuid"],
                event_type="user_created",
                actor_subject=actor_subject,
                payload={"email": row["email"]},
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictAppError(f"An account already exists for {email!r}") from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise DatabaseUnavailableError("Unable to create account") from exc

        logger.warning("admin_account_created auth_subject=%s email=%s", actor_subject, row["email"])
        return dict(row)

    def delete_account(
        self,
        *,
        user_uuid: str,
        approval_code: str | None,
        actor_subject: str,
        reason: str | None,
    ) -> dict:
        # Fail closed before touching the database: no valid code, no mutation.
        require_account_approval(approval_code)

        try:
            row = (
                self._session.execute(
                    text(
                        """
                        UPDATE iam.users
                        SET is_active = false, updated_by = :actor_subject, updated_at = now()
                        WHERE user_uuid = CAST(:user_uuid AS uuid) AND is_active = true
                        RETURNING user_uuid::text AS user_uuid, email, is_active
                        """
                    ),
                    {"user_uuid": user_uuid, "actor_subject": actor_subject},
                )
                .mappings()
                .first()
            )
            if row is None:
                self._session.rollback()
                raise NotFoundAppError(f"No active account {user_uuid!r}")

            self._log_event(
                user_uuid=row["user_uuid"],
                event_type="user_deleted_via_admin_api",
                actor_subject=actor_subject,
                payload={"reason": reason or ""},
            )
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise DatabaseUnavailableError("Unable to delete account") from exc

        logger.warning(
            "admin_account_deleted auth_subject=%s user_uuid=%s reason=%s",
            actor_subject,
            row["user_uuid"],
            reason or "",
        )
        return dict(row)

    def _log_event(self, *, user_uuid: str, event_type: str, actor_subject: str, payload: dict) -> None:
        self._session.execute(
            text(
                """
                INSERT INTO iam.user_api_key_events (
                    user_uuid, event_type, actor_type, actor_subject, event_payload
                ) VALUES (
                    CAST(:user_uuid AS uuid), :event_type, 'admin', :actor_subject, CAST(:payload AS jsonb)
                )
                """
            ),
            {
                "user_uuid": user_uuid,
                "event_type": event_type,
                "actor_subject": actor_subject,
                "payload": json.dumps(payload),
            },
        )
