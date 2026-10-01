"""IAM critical paths against real Postgres, executed as the api_service role."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import audit
from app.auth.models import PrincipalType
from app.auth.service_clients import get_service_client, verify_service_client_secret
from app.auth.user_api_keys import verify_user_api_key
from app.core.config import settings
from app.domain.errors import AuthenticationError, ConflictAppError
from app.repositories.sql_refresh_tokens import RefreshTokenRepository, mint_refresh_token_value
from app.services.account_service import AccountService


def _unique(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}"


def _owner_row(owner_engine: Engine, sql: str, **params) -> dict | None:
    with owner_engine.connect() as conn:
        row = conn.execute(text(sql), params).mappings().first()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Service-client credentials (app/auth/service_clients.py, database mode)
# ---------------------------------------------------------------------------


def test_service_client_database_auth_round_trip(
    owner_engine: Engine, app_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "service_client_auth_mode", "database")
    client_id = _unique("it-client")
    issued = _owner_row(
        owner_engine,
        "SELECT client_uuid::text AS client_uuid, api_key, granted_scopes "
        "FROM iam.provision_service_client(:client_id, 'IT client', 'vi-backend', 'development', 'pytest')",
        client_id=client_id,
    )
    assert issued is not None

    client = get_service_client(client_id, session=app_session)
    assert client.client_uuid == issued["client_uuid"]
    assert sorted(client.scopes) == sorted(issued["granted_scopes"])

    verify_service_client_secret(client, issued["api_key"], session=app_session, client_ip="203.0.113.7")

    used = _owner_row(
        owner_engine,
        "SELECT host(last_used_ip) AS ip, last_used_at FROM iam.service_client_secrets "
        "WHERE client_uuid = CAST(:uuid AS uuid)",
        uuid=issued["client_uuid"],
    )
    assert used is not None
    assert used["ip"] == "203.0.113.7"
    assert used["last_used_at"] is not None
    event = _owner_row(
        owner_engine,
        "SELECT actor_subject FROM iam.service_client_events "
        "WHERE client_uuid = CAST(:uuid AS uuid) AND event_type = 'service_token_issued'",
        uuid=issued["client_uuid"],
    )
    assert event == {"actor_subject": f"service:{client_id}"}

    with pytest.raises(AuthenticationError):
        verify_service_client_secret(client, issued["api_key"] + "x", session=app_session)


def test_disabled_service_client_is_unknown(
    owner_engine: Engine, app_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "service_client_auth_mode", "database")
    client_id = _unique("it-disabled")
    issued = _owner_row(
        owner_engine,
        "SELECT api_key FROM iam.provision_service_client(:client_id, 'Integration test client', 'vi-backend', 'development', 'pytest')",
        client_id=client_id,
    )
    client = get_service_client(client_id, session=app_session)

    with owner_engine.connect() as conn:
        conn.execute(text("UPDATE iam.service_clients SET is_active = false WHERE client_id = :c"), {"c": client_id})

    with pytest.raises(AuthenticationError, match="Unknown service client"):
        get_service_client(client_id, session=app_session)
    # The disable trigger also revoked the secret, so a cached client object fails too.
    with pytest.raises(AuthenticationError):
        verify_service_client_secret(client, issued["api_key"], session=app_session)


# ---------------------------------------------------------------------------
# User API keys + admin account lifecycle
# ---------------------------------------------------------------------------


def _provision_user_key(owner_engine: Engine, email: str) -> dict:
    row = _owner_row(
        owner_engine,
        "SELECT user_uuid::text AS user_uuid, key_uuid::text AS key_uuid, api_key "
        "FROM iam.provision_user_api_key(:email, 'IT user', 'it key', ARRAY['market:read'], 'pytest', 'free', "
        "now() + interval '30 days')",
        email=email,
    )
    assert row is not None
    return row


def test_user_api_key_verifies_then_dies_with_account(
    owner_engine: Engine, app_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    issued = _provision_user_key(owner_engine, f"{_unique('it')}@example.com")

    principal = verify_user_api_key(issued["api_key"], session=app_session, client_ip="198.51.100.4")
    assert principal.subject == f"user:{issued['user_uuid']}"
    assert principal.principal_type == PrincipalType.USER
    assert principal.scopes == frozenset({"market:read"})

    monkeypatch.setattr(settings, "admin_account_approval_code", "it-approval-code")
    result = AccountService(app_session).delete_account(
        user_uuid=issued["user_uuid"],
        approval_code="it-approval-code",
        actor_subject="service:admin-tool",
        reason="integration test",
    )
    assert result["is_active"] is False

    key = _owner_row(
        owner_engine,
        "SELECT is_active, revoked_reason FROM iam.user_api_keys WHERE key_uuid = CAST(:k AS uuid)",
        k=issued["key_uuid"],
    )
    assert key == {"is_active": False, "revoked_reason": "user disabled"}

    with pytest.raises(AuthenticationError, match="Invalid API key"):
        verify_user_api_key(issued["api_key"], session=app_session)
    rejected = _owner_row(
        owner_engine,
        "SELECT event_payload ->> 'reason' AS reason FROM iam.user_api_key_events "
        "WHERE key_uuid = CAST(:k AS uuid) AND event_type = 'key_rejected' ORDER BY event_id DESC LIMIT 1",
        k=issued["key_uuid"],
    )
    assert rejected == {"reason": "key_revoked"}


def test_expired_user_api_key_is_rejected(owner_engine: Engine, app_session: Session) -> None:
    issued = _provision_user_key(owner_engine, f"{_unique('it')}@example.com")
    with owner_engine.connect() as conn:
        conn.execute(
            text("UPDATE iam.user_api_keys SET expires_at = now() - interval '1 second' WHERE key_uuid = CAST(:k AS uuid)"),
            {"k": issued["key_uuid"]},
        )
    with pytest.raises(AuthenticationError, match="API key expired"):
        verify_user_api_key(issued["api_key"], session=app_session)


def test_account_create_list_and_duplicate(app_session: Session) -> None:
    service = AccountService(app_session)
    email = f"{_unique('It-Create')}@Example.com"
    created = service.create_account(
        email=email, display_name="IT", organization=None, plan="free", actor_subject="service:admin-tool"
    )
    assert created["email"] == email.lower()
    assert created["is_active"] is True
    assert any(row["user_uuid"] == created["user_uuid"] for row in service.list_accounts())

    with pytest.raises(ConflictAppError):
        service.create_account(
            email=email, display_name=None, organization=None, plan="free", actor_subject="service:admin-tool"
        )


# ---------------------------------------------------------------------------
# Refresh tokens (rotate-on-use, reuse rejected)
# ---------------------------------------------------------------------------


def test_refresh_token_rotation_rejects_reuse(app_session: Session) -> None:
    repo = RefreshTokenRepository(app_session)
    client_id = _unique("it-refresh")
    expires = datetime.now(UTC) + timedelta(days=1)
    first = mint_refresh_token_value()
    repo.insert(subject=f"service:{client_id}", client_id=client_id, raw_token=first, scopes=["market:read"], expires_at=expires)

    second = mint_refresh_token_value()
    rotated = repo.rotate(presented_raw_token=first, new_raw_token=second, new_expires_at=expires)
    assert rotated.scopes == ["market:read"]
    assert repo.lookup_active(second).id == rotated.id

    with pytest.raises(AuthenticationError, match="already used or revoked"):
        repo.rotate(presented_raw_token=first, new_raw_token=mint_refresh_token_value(), new_expires_at=expires)

    repo.revoke_active_for_client(client_id)
    with pytest.raises(AuthenticationError):
        repo.lookup_active(second)


# ---------------------------------------------------------------------------
# Scope-denial audit log (errors are swallowed at runtime, so test the grant)
# ---------------------------------------------------------------------------


def test_auth_audit_row_is_written_as_api_service(
    owner_engine: Engine, app_sessionmaker: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit, "get_db_session", app_sessionmaker)
    subject = _unique("service:it-audit")
    audit.record_auth_audit(
        subject=subject, scope_required="admin:read", scope_granted="market:read", route="/api/v1/admin/x", outcome="forbidden"
    )
    row = _owner_row(owner_engine, "SELECT outcome FROM iam.auth_audit_log WHERE subject = :s", s=subject)
    assert row == {"outcome": "forbidden"}


# ---------------------------------------------------------------------------
# Least privilege: what api_service must never be able to do
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        # iam: no deletes, no identity edits, no self-granted scopes
        "DELETE FROM iam.users WHERE false",
        "UPDATE iam.users SET email = email WHERE false",
        "INSERT INTO iam.service_client_scopes (client_uuid, scope) VALUES (gen_random_uuid(), 'admin:*')",
        "UPDATE iam.service_clients SET is_active = true WHERE false",
        "TRUNCATE iam.auth_audit_log",
        # theeyebeta (Prod-owned): read-only, no DDL, no policy writes
        "INSERT INTO theeyebeta.prices_daily (instrument_id, ts, open, high, low, close, volume, source)"
        " VALUES (1, now(), 1, 1, 1, 1, 1, 'x')",
        "UPDATE theeyebeta.instruments SET symbol = symbol WHERE false",
        "DELETE FROM theeyebeta.market_news WHERE false",
        "TRUNCATE theeyebeta.audit_log",
        "UPDATE theeyebeta.dataapi_locks SET active = false WHERE false",
        "INSERT INTO theeyebeta.dataapi_credential_revocations (token_id, expires_at) VALUES ('x', now())",
        "CREATE TABLE theeyebeta.escalation (id int)",
        "ALTER TABLE theeyebeta.instruments ADD COLUMN pwned int",
        "DROP TABLE theeyebeta.market_news",
        "CREATE TABLE iam.escalation (id int)",
        # Prod-internal objects outside the allowlist stay invisible
        "SELECT 1 FROM theeyebeta.signals LIMIT 1",
        "SELECT 1 FROM theeyebeta.prices_intraday LIMIT 1",
        # no role or privilege escalation
        "SET ROLE postgres",
        "ALTER ROLE api_service SUPERUSER",
        "CREATE ROLE escalation LOGIN",
    ],
)
def test_api_service_privilege_boundary(app_session: Session, statement: str) -> None:
    with pytest.raises(ProgrammingError) as denied:
        app_session.execute(text(statement))
    app_session.rollback()
    assert isinstance(denied.value.orig, psycopg.errors.InsufficientPrivilege), denied.value


@pytest.mark.parametrize(
    "table",
    ["instruments", "prices_daily", "market_news", "latest_snapshots", "fundamentals", "audit_log"],
)
def test_api_service_reads_allowlisted_market_tables(app_session: Session, table: str) -> None:
    app_session.execute(text(f"SELECT 1 FROM theeyebeta.{table} LIMIT 1"))


@pytest.mark.parametrize(
    "table",
    ["dataapi_locks", "dataapi_credential_revocations", "dataapi_entitlements", "dataapi_applications"],
)
def test_api_service_reads_policy_tables_through_prod_api_readonly(
    owner_engine: Engine, app_session: Session, table: str
) -> None:
    app_session.execute(text(f"SELECT 1 FROM theeyebeta.{table} LIMIT 1"))
    # The access comes from membership in Prod's role, not a DataAPI grant.
    direct = _owner_row(
        owner_engine,
        "SELECT count(*) AS n FROM information_schema.role_table_grants "
        "WHERE grantee = 'api_service' AND table_schema = 'theeyebeta' AND table_name = :t",
        t=table,
    )
    assert direct == {"n": 0}


def test_api_service_is_not_owner_or_superuser(owner_engine: Engine) -> None:
    row = _owner_row(
        owner_engine,
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, "
        "pg_has_role('api_service', 'api_readonly', 'MEMBER') AS in_api_readonly, "
        "(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        " WHERE n.nspname IN ('theeyebeta', 'iam') AND pg_get_userbyid(c.relowner) = 'api_service') AS owned "
        "FROM pg_roles WHERE rolname = 'api_service'",
    )
    assert row == {
        "rolsuper": False,
        "rolcreaterole": False,
        "rolcreatedb": False,
        "rolbypassrls": False,
        "in_api_readonly": True,
        "owned": 0,
    }
