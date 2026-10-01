"""Build a disposable PostgreSQL database that mirrors production's layout.

Used by tests/integration (IAM SQL + grants) and tests/contract (HTTP API
against TheEyeBetaProd's schema). Layers, in the order production gets them:

1. contracts/prod/theeyebeta_schema.sql  - Prod-owned theeyebeta objects
   DataAPI reads, generated from TheEyeBetaProd's migrations at
   contracts/prod/PROD_SHA (scripts/prod_contract_snapshot.sh);
2. contracts/prod/api_readonly_grants.sql - the role/grants Prod gives DataAPI;
3. deploy/iam_*.sql                       - DataAPI-owned iam schema;
4. deploy/db_security.sql                 - the api_service login role.

Never point any of this at a real server: callers must pass a scratch
superuser URL and every database it creates is dropped afterwards.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from sqlalchemy.engine import URL

REPO_ROOT = Path(__file__).resolve().parents[1]
PROD_CONTRACT_DIR = REPO_ROOT / "contracts" / "prod"
IAM_SQL_FILES = (
    "iam_api_key_schema.sql",
    "iam_user_api_key_schema.sql",
    "iam_refresh_tokens.sql",
    "iam_auth_audit.sql",
)
APP_ROLE = "api_service"
SAFE_DB_PREFIXES = ("dataapi_it_", "dataapi_contract")
SAFE_HOSTS = {"127.0.0.1", "localhost", "::1", "postgres"}


def libpq(url: URL) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def assert_scratch(url: URL) -> None:
    """Refuse anything that does not look like a disposable local database."""
    if url.host not in SAFE_HOSTS:
        raise RuntimeError(f"refusing to build test schema on non-local host {url.host!r}")
    if not (url.database or "").startswith(SAFE_DB_PREFIXES):
        raise RuntimeError(f"refusing to build test schema in database {url.database!r}")


def run_sql_file(conninfo: str, path: Path) -> None:
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(path.read_text(encoding="utf-8"))


def create_database(admin_url: URL, db_name: str) -> URL:
    target = admin_url.set(database=db_name)
    assert_scratch(target)
    with psycopg.connect(libpq(admin_url), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{db_name}"')
    return target


def drop_database(admin_url: URL, db_name: str) -> None:
    with psycopg.connect(libpq(admin_url), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')


def build_production_layout(owner_url: URL, app_password: str) -> None:
    """Apply all four layers to an empty scratch database."""
    assert_scratch(owner_url)
    conninfo = libpq(owner_url)
    run_sql_file(conninfo, PROD_CONTRACT_DIR / "theeyebeta_schema.sql")
    run_sql_file(conninfo, PROD_CONTRACT_DIR / "api_readonly_grants.sql")
    for name in IAM_SQL_FILES:
        run_sql_file(conninfo, REPO_ROOT / "deploy" / name)
    run_sql_file(conninfo, REPO_ROOT / "deploy" / "db_security.sql")
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            psycopg.sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                psycopg.sql.Identifier(APP_ROLE), psycopg.sql.Literal(app_password)
            )
        )
