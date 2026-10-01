"""HTTP contract tests: this API against TheEyeBetaProd's real schema.

Opt-in (CI job `prod-contract`). Requires, at process start:

  PROD_CONTRACT=1
  TEST_POSTGRES_URL=postgresql+psycopg://postgres:...@127.0.0.1:5432/postgres   (scratch superuser)
  DATABASE_URL=postgresql+psycopg://api_service:<pw>@127.0.0.1:5432/dataapi_contract
  SERVICE_CLIENT_AUTH_MODE=database
  POLICY_ENFORCEMENT_ENABLED=true

The app binds its engine to DATABASE_URL at import, so the database named
there is created here before the first request: Prod schema snapshot + Prod
api_readonly grants + iam SQL + db_security.sql (tests/pg_support.py) + seed
rows. Requests then run as api_service, exactly like production.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests.pg_support import APP_ROLE, build_production_layout, create_database, drop_database, libpq, run_sql_file

ENABLED = os.environ.get("PROD_CONTRACT") == "1"
SEED_SQL = Path(__file__).with_name("seed.sql")

# Scopes as the consumers request them (verified in their repositories).
LENS_CLIENT = "ai-advisor-production"
LENS_SCOPES = ("advisor:read", "market:read", "signals:read", "symbols:read")
ADMIN_BRIDGE_CLIENT = "theeyebeta-prod-admin"
# TheEyeBetaProd services/admin_service/settings.py dataapi_scopes default @ PROD_SHA
ADMIN_BRIDGE_SCOPES = (
    "advisor:read",
    "market:read",
    "symbols:read",
    "analytics:read",
    "signals:read",
    "portfolio:read",
    "admin:read",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if ENABLED:
        return
    skip = pytest.mark.skip(reason="Prod contract gate runs in the prod-contract CI job (PROD_CONTRACT=1)")
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(skip)


@dataclass(frozen=True)
class ServiceCredential:
    client_id: str
    secret: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class ContractEnv:
    lens: ServiceCredential
    admin_bridge: ServiceCredential


def _provision(conn: psycopg.Connection, client_id: str, app_type: str, scopes: tuple[str, ...]) -> ServiceCredential:
    row = conn.execute(
        "SELECT client_uuid, api_key FROM iam.provision_service_client(%s, %s, %s, 'production', 'contract-tests')",
        (client_id, f"{client_id} (contract)", app_type),
    ).fetchone()
    assert row is not None
    client_uuid, api_key = row
    # Exact production scope set, not the app_type template.
    conn.execute("DELETE FROM iam.service_client_scopes WHERE client_uuid = %s", (client_uuid,))
    for scope in scopes:
        conn.execute(
            "INSERT INTO iam.service_client_scopes (client_uuid, scope, grant_source, granted_by)"
            " VALUES (%s, %s, 'manual', 'contract-tests')",
            (client_uuid, scope),
        )
    return ServiceCredential(client_id=client_id, secret=api_key, scopes=scopes)


@pytest.fixture(scope="session")
def contract_env() -> Iterator[ContractEnv]:
    from app.core.config import settings

    app_url = make_url(os.environ["DATABASE_URL"])
    admin_url = make_url(os.environ["TEST_POSTGRES_URL"])
    if app_url.username != APP_ROLE or app_url.database != "dataapi_contract":
        raise RuntimeError("DATABASE_URL must be api_service@.../dataapi_contract for the contract gate")
    assert settings.service_client_auth_mode == "database"
    assert settings.policy_enforcement_enabled is True

    owner_url = create_database(admin_url, app_url.database)
    try:
        build_production_layout(owner_url, app_url.password or "")
        run_sql_file(libpq(owner_url), SEED_SQL)
        with psycopg.connect(libpq(owner_url), autocommit=True) as conn:
            lens = _provision(conn, LENS_CLIENT, "mobile-backend", LENS_SCOPES)
            bridge = _provision(conn, ADMIN_BRIDGE_CLIENT, "admin-tool", ADMIN_BRIDGE_SCOPES)
        yield ContractEnv(lens=lens, admin_bridge=bridge)
    finally:
        from app.db.session import engine

        engine.dispose()
        drop_database(admin_url, app_url.database)
