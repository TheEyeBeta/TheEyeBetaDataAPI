"""Synchronous repository for low-volume DataAPI policy state."""

from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.models import Principal
from app.domain.errors import AuthenticationError, AuthorizationError, DatabaseUnavailableError


@dataclass(frozen=True)
class DelegationGrant:
    """Tenant and policy attributes verified before issuing a delegated token."""

    tenant_id: str
    policy_version: int


class PolicyRepository:
    """Evaluate DataAPI policy using fully-qualified, bounded SQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def grant_lens_delegation(self, *, client_id: str, subject: str) -> DelegationGrant:
        row = self._session.execute(
            text(
                """
                SELECT app.tenant_id::text AS tenant_id, pv.version AS policy_version
                FROM theeyebeta.dataapi_applications app
                JOIN theeyebeta.dataapi_tenants tenant ON tenant.id = app.tenant_id
                JOIN theeyebeta.dataapi_memberships membership
                  ON membership.tenant_id = tenant.id
                 AND membership.external_subject = :subject
                JOIN theeyebeta.dataapi_policy_versions pv
                  ON pv.status = 'ACTIVE'
                 AND pv.effective_from <= now()
                JOIN theeyebeta.dataapi_entitlements entitlement
                  ON entitlement.tenant_id = tenant.id
                 AND entitlement.policy_version_id = pv.id
                 AND entitlement.code = 'LENS_ACCESS'
                 AND entitlement.status = 'ACTIVE'
                WHERE app.client_id = :client_id
                  AND app.product = 'LENS'
                  AND app.status = 'ACTIVE'
                  AND tenant.status = 'ACTIVE'
                  AND membership.status = 'ACTIVE'
                ORDER BY pv.version DESC
                LIMIT 1
                """
            ),
            {"client_id": client_id, "subject": subject},
        ).mappings().first()
        if not row:
            raise AuthorizationError("Lens delegation is not entitled")
        self._assert_not_locked(
            tenant_id=str(row["tenant_id"]), client_id=client_id, subject=subject, token_id=None
        )
        return DelegationGrant(tenant_id=str(row["tenant_id"]), policy_version=int(row["policy_version"]))

    def enforce(self, principal: Principal) -> None:
        """Reject revoked, suspended, or unentitled delegated principals."""
        if principal.delegated:
            if not principal.tenant_id or not principal.client_id or principal.policy_version is None:
                raise AuthorizationError("Delegated principal has no tenant binding")
            active = self._session.execute(
                text(
                    """
                    SELECT 1
                    FROM theeyebeta.dataapi_applications app
                    JOIN theeyebeta.dataapi_tenants tenant ON tenant.id = app.tenant_id
                    JOIN theeyebeta.dataapi_memberships membership
                      ON membership.tenant_id = tenant.id
                     AND membership.external_subject = :subject
                    JOIN theeyebeta.dataapi_policy_versions policy
                      ON policy.version = :policy_version
                     AND policy.status = 'ACTIVE'
                     AND policy.effective_from <= now()
                    JOIN theeyebeta.dataapi_entitlements entitlement
                      ON entitlement.tenant_id = tenant.id
                     AND entitlement.policy_version_id = policy.id
                     AND entitlement.code = 'LENS_ACCESS'
                     AND entitlement.status = 'ACTIVE'
                    WHERE app.client_id = :client_id
                      AND app.tenant_id = CAST(:tenant_id AS uuid)
                      AND app.product = 'LENS'
                      AND app.status = 'ACTIVE'
                      AND tenant.status = 'ACTIVE'
                      AND membership.status = 'ACTIVE'
                    LIMIT 1
                    """
                ),
                {
                    "client_id": principal.client_id,
                    "tenant_id": principal.tenant_id,
                    "subject": principal.subject,
                    "policy_version": principal.policy_version,
                },
            ).first()
            if not active:
                raise AuthorizationError("Delegated principal is no longer entitled")
            self._assert_not_locked(
                tenant_id=principal.tenant_id,
                client_id=principal.client_id,
                subject=principal.subject,
                token_id=principal.token_id,
            )
            return
        if principal.principal_type.value == "service" and principal.client_id:
            self._assert_not_locked(
                tenant_id=None, client_id=principal.client_id, subject=None, token_id=principal.token_id
            )

    def _assert_not_locked(
        self,
        *,
        tenant_id: str | None,
        client_id: str | None,
        subject: str | None,
        token_id: str | None,
    ) -> None:
        scopes = [("GLOBAL", "*"), ("TENANT", tenant_id), ("APPLICATION", client_id), ("SUBJECT", subject), ("CREDENTIAL", token_id)]
        active_scopes = [(scope_type, scope_id) for scope_type, scope_id in scopes if scope_id]
        if not active_scopes:
            return
        clauses = " OR ".join(
            f"(scope_type = :scope_type_{index} AND scope_id = :scope_id_{index})"
            for index, _ in enumerate(active_scopes)
        )
        params: dict[str, object] = {}
        for index, (scope_type, scope_id) in enumerate(active_scopes):
            params[f"scope_type_{index}"] = scope_type
            params[f"scope_id_{index}"] = scope_id
        lock = self._session.execute(
            text(
                f"""
                SELECT id
                FROM theeyebeta.dataapi_locks
                WHERE active = true
                  AND (expires_at IS NULL OR expires_at > now())
                  AND ({clauses})
                LIMIT 1
                """
            ),
            params,
        ).first()
        if lock:
            raise AuthorizationError("Access is currently locked")
        if token_id:
            revoked = self._session.execute(
                text(
                    """
                    SELECT id
                    FROM theeyebeta.dataapi_credential_revocations
                    WHERE token_id = :token_id
                      AND expires_at > now()
                    LIMIT 1
                    """
                ),
                {"token_id": token_id},
            ).first()
            if revoked:
                raise AuthenticationError("Credential has been revoked")


def enforce_policy(session: Session, principal: Principal) -> None:
    """Translate database failures into fail-closed authorization responses."""
    try:
        PolicyRepository(session).enforce(principal)
    except (AuthenticationError, AuthorizationError):
        raise
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError("Policy service is unavailable") from exc
